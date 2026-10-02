"""Redis 裁决层（db-to-http 迁移 §8.1，2026-10-02 落地）。

http_backend 仓储"读-改-写"退化路径的进程间互斥裁决点：任务状态机 CAS、
Sheet 占用、token 计数回写、回测/调度运行锁的临界区串行化。

设计要点：

- **只串行化秒级读-改-写临界区**：持久状态仍在远端行（Redis 锁不承载业务
  语义），TTL 到期自动放行、持有者崩溃不留死锁，因此不引入长持锁与续期；
- **降级直通**：REDIS_URL 未配置 / redis 依赖缺失 / 连接异常时，锁恒成功
  （等价接入前的读-改-写现状，单 worker 部署语义本就安全），首次降级打
  一条 warning；
- 锁值含持有者 token，释放用 Lua 校验防误删他人锁；
- 命名空间 ``{namespace}:*``；启动期 ``namespace_reset()`` 清理本应用残留
  锁（对齐 db 模式 startup 占用重置语义，多副本共库经 REDIS_NAMESPACE 隔离）。

零 Flask 依赖，http_backend 仓储可直接 import（与 app/remote_api 同级的基础模块）。
"""

from __future__ import annotations

import logging
import os
import secrets
import time
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# 直通模式哨兵：降级（未配置/不可用）时 acquire 返回它，release 对它直接成功。
_PASSTHROUGH_TOKEN = "passthrough"

# 竞争等待的重试间隔；等待预算耗尽后降级直行（TTL 兜底不会长期阻塞）。
_RETRY_INTERVAL_SECONDS = 0.2

# 释放/续期必须校验持有者，防止 TTL 过期后误删他人锁。
_RELEASE_SCRIPT = (
    "if redis.call('get', KEYS[1]) == ARGV[1] "
    "then return redis.call('del', KEYS[1]) else return 0 end"
)
_RENEW_SCRIPT = (
    "if redis.call('get', KEYS[1]) == ARGV[1] "
    "then return redis.call('pexpire', KEYS[1], ARGV[2]) else return 0 end"
)


class RedisArbiter:
    """进程间互斥裁决器；client 可注入（测试替身），REDIS_URL 为空时直通。"""

    def __init__(self, client=None, url="", namespace="arb:gstask"):
        self._client = client
        self._url = (url or "").strip()
        self.namespace = (namespace or "arb:gstask").strip()
        self._warned = False

    @classmethod
    def from_env(cls):
        return cls(
            url=os.environ.get("REDIS_URL", ""),
            namespace=os.environ.get("REDIS_NAMESPACE", "arb:gstask"),
        )

    # ---- 基础设施 ----

    def _degrade_once(self, reason):
        if not self._warned:
            self._warned = True
            logger.warning("Redis 裁决层降级为直通（读-改-写互斥失效，单 worker 部署仍安全）：%s", reason)

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        if not self._url:
            self._degrade_once("REDIS_URL 未配置")
            return None
        try:
            import redis  # 延迟导入：依赖缺失时降级而非崩掉业务路径
        except ImportError:
            self._degrade_once("redis 依赖未安装（pip install redis）")
            return None
        try:
            self._client = redis.Redis.from_url(
                self._url,
                socket_timeout=2,
                socket_connect_timeout=2,
                decode_responses=True,
            )
        except Exception as exc:
            self._degrade_once(f"Redis 客户端构造失败: {exc}")
            return None
        return self._client

    def _key(self, name):
        return f"{self.namespace}:{name}"

    # ---- 锁原语 ----

    def acquire(self, name, ttl_seconds=15):
        """获取互斥锁：成功返回持有者 token；竞争返回 None；降级返回哨兵。"""
        client = self._ensure_client()
        if client is None:
            return _PASSTHROUGH_TOKEN
        token = secrets.token_hex(8)
        try:
            ok = client.set(self._key(name), token, nx=True, ex=max(1, int(ttl_seconds)))
        except Exception as exc:
            self._degrade_once(f"获取锁异常（{name}）: {exc}")
            return _PASSTHROUGH_TOKEN
        return token if ok else None

    def release(self, name, token):
        """释放锁（Lua 校验持有者）；降级 token 恒成功。"""
        if token == _PASSTHROUGH_TOKEN:
            return True
        try:
            return bool(self._run_script(_RELEASE_SCRIPT, self._key(name), [token]))
        except Exception as exc:
            logger.warning("Redis 释放锁异常（%s）: %s", name, exc)
            return False

    def renew(self, name, token, ttl_seconds=15):
        """续期（校验持有者）。当前临界区均为秒级、无需续期，留作长临界区扩展。"""
        if token == _PASSTHROUGH_TOKEN:
            return True
        try:
            return bool(
                self._run_script(
                    _RENEW_SCRIPT, self._key(name), [token, int(ttl_seconds * 1000)]
                )
            )
        except Exception as exc:
            logger.warning("Redis 续期异常（%s）: %s", name, exc)
            return False

    def _run_script(self, script_text, key, args):
        """经 redis-py register_script 执行 Lua（服务端原子校验持有者）。"""
        runner = self._client.register_script(script_text)
        return runner(keys=[key], args=list(args))

    def namespace_reset(self):
        """启动期清理本命名空间残留锁；返回删除键数（降级/空返回 0）。"""
        client = self._ensure_client()
        if client is None:
            return 0
        deleted = 0
        batch = []
        try:
            for key in client.scan_iter(match=f"{self.namespace}:*", count=200):
                batch.append(key)
                if len(batch) >= 200:
                    deleted += client.delete(*batch)
                    batch = []
            if batch:
                deleted += client.delete(*batch)
        except Exception as exc:
            self._degrade_once(f"命名空间清理异常: {exc}")
            return 0
        if deleted:
            logger.info("Redis 裁决层启动清理：%s 命名空间删除 %d 个残留锁", self.namespace, deleted)
        return deleted

    # ---- 便捷入口 ----

    @contextmanager
    def mutex(self, name, ttl_seconds=15, wait_seconds=5.0):
        """临界区互斥：等待预算内重试获取，超时降级直行（等价接入前语义）。"""
        token = None
        deadline = time.monotonic() + max(0.0, wait_seconds)
        while True:
            token = self.acquire(name, ttl_seconds)
            if token is not None:
                break
            if time.monotonic() >= deadline:
                logger.warning("裁决锁竞争超时（%s），降级直行", name)
                token = _PASSTHROUGH_TOKEN
                break
            time.sleep(_RETRY_INTERVAL_SECONDS)
        try:
            yield token != _PASSTHROUGH_TOKEN
        finally:
            self.release(name, token)


# ---- 进程内单例（启动期/首用时读环境变量；测试经 configure_arbiter 注入替身） ----

_arbiter = None


def get_arbiter() -> RedisArbiter:
    global _arbiter
    if _arbiter is None:
        _arbiter = RedisArbiter.from_env()
    return _arbiter


def configure_arbiter(arbiter) -> None:
    global _arbiter
    _arbiter = arbiter
