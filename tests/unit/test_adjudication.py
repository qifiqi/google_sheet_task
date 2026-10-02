"""Redis 裁决层（app/adjudication.py）单元测试。

FakeRedis 以字典语义模拟 SET NX EX / GET / DEL / PEXPIRE / SCAN /
register_script（release/renew 两条 Lua 脚本按语义等价实现），全套件零网络
依赖。真实 Redis 行为（脚本语法/网络）以部署冒烟为准。
"""
import fnmatch
import threading
import time

from app.adjudication import RedisArbiter, configure_arbiter, get_arbiter


class FakeRedis:
    """redis-py 客户端的最小替身：覆盖裁决层用到的命令集。"""

    def __init__(self):
        self.data = {}
        self.expiry_at = {}  # key -> monotonic 毫秒

    # ---- 过期模拟 ----

    def _expire(self, key):
        deadline = self.expiry_at.get(key)
        if deadline is not None and time.monotonic() * 1000 >= deadline:
            self.data.pop(key, None)
            self.expiry_at.pop(key, None)

    # ---- 命令 ----

    def set(self, key, value, nx=False, ex=None):
        self._expire(key)
        if nx and key in self.data:
            return None
        self.data[key] = value
        if ex is not None:
            self.expiry_at[key] = time.monotonic() * 1000 + ex * 1000
        return True

    def get(self, key):
        self._expire(key)
        return self.data.get(key)

    def delete(self, *keys):
        deleted = 0
        for key in keys:
            self._expire(key)
            if key in self.data:
                del self.data[key]
                self.expiry_at.pop(key, None)
                deleted += 1
        return deleted

    def pexpire(self, key, milliseconds):
        if self.get(key) is not None:
            self.expiry_at[key] = time.monotonic() * 1000 + milliseconds
            return 1
        return 0

    def scan_iter(self, match=None, count=None):
        for key in list(self.data):
            if match is None or fnmatch.fnmatch(key, match):
                yield key

    def register_script(self, script):
        """返回可调用 Script 对象；按脚本语义等价执行（先校验持有者 token）。"""

        def _runner(keys=None, args=None, client=None):
            key = (keys or [None])[0]
            argv = list(args or [])
            current = self.get(key)
            if "pexpire" in script:  # renew：续期
                if current == argv[0]:
                    self.expiry_at[key] = time.monotonic() * 1000 + int(argv[1])
                    return 1
                return 0
            if current == argv[0]:  # release：删除
                self.delete(key)
                return 1
            return 0

        return _runner


def _arbiter(fake, namespace="arb:test"):
    return RedisArbiter(client=fake, url="redis://fake", namespace=namespace)


def test_acquire_release_and_contention():
    fake = FakeRedis()
    a = _arbiter(fake)
    token = a.acquire("task:t1:state", ttl_seconds=15)
    assert token is not None
    assert fake.data["arb:test:task:t1:state"] == token

    # 第二持有者竞争失败
    assert a.acquire("task:t1:state") is None
    # 非持有者 token 释放被拒（Lua 校验）
    assert a.release("task:t1:state", "wrong-token") is False
    # 持有者释放成功，随后可重新获取
    assert a.release("task:t1:state", token) is True
    assert a.acquire("task:t1:state") is not None


def test_mutex_serializes_and_frees():
    fake = FakeRedis()
    a = _arbiter(fake)
    with a.mutex("sheet:9:occupy", ttl_seconds=30) as held:
        assert held is True
        # 临界区内：同键第二个仲裁器拿不到锁
        b = _arbiter(fake)
        assert b.acquire("sheet:9:occupy") is None
    # 退出后锁归还
    assert a.acquire("sheet:9:occupy") is not None


def test_mutex_degrades_after_wait_timeout():
    fake = FakeRedis()
    holder = _arbiter(fake)
    holder.acquire("btlock:s1", ttl_seconds=60)

    waiter = _arbiter(fake)
    with waiter.mutex("btlock:s1", wait_seconds=0) as held:
        # 竞争超时降级直行：等价接入前语义，业务路径不中断
        assert held is False


def test_ttl_expiry_releases_stale_lock():
    fake = FakeRedis()
    a = _arbiter(fake)
    # 手工注入一把已过期锁（模拟持有者崩溃后 TTL 到期）
    fake.data["arb:test:task:t2:state"] = "ghost"
    fake.expiry_at["arb:test:task:t2:state"] = time.monotonic() * 1000 - 1
    assert a.acquire("task:t2:state") is not None


def test_namespace_reset_only_touches_own_namespace():
    fake = FakeRedis()
    a = _arbiter(fake)
    fake.data["arb:test:a"] = "1"
    fake.data["arb:test:b"] = "1"
    fake.data["arb:other:x"] = "1"
    fake.data["unrelated"] = "1"
    assert a.namespace_reset() == 2
    assert "arb:test:a" not in fake.data
    assert fake.data["arb:other:x"] == "1"
    assert fake.data["unrelated"] == "1"


def test_renew_extends_for_holder_only():
    fake = FakeRedis()
    a = _arbiter(fake)
    token = a.acquire("sched:t3:run", ttl_seconds=1)
    assert a.renew("sched:t3:run", token, ttl_seconds=60) is True
    assert a.renew("sched:t3:run", "wrong", ttl_seconds=60) is False


def test_passthrough_when_unconfigured():
    a = RedisArbiter(url="")
    assert a.acquire("any") == "passthrough"
    assert a.release("any", "passthrough") is True
    with a.mutex("any") as held:
        assert held is False  # 直通模式不持锁
    assert a.namespace_reset() == 0


def test_singleton_and_injection():
    # conftest 已固定 REDIS_URL=""，进程单例应为直通模式
    assert get_arbiter().acquire("x") == "passthrough"
    fake = FakeRedis()
    try:
        configure_arbiter(_arbiter(fake, namespace="arb:injected"))
        assert get_arbiter().acquire("k") is not None
    finally:
        configure_arbiter(None)
    assert get_arbiter().acquire("x") == "passthrough"


def test_cross_thread_mutual_exclusion():
    fake = FakeRedis()
    a = _arbiter(fake)
    order = []

    def worker(name):
        with a.mutex("gsheet-token:in-use-counts", ttl_seconds=30):
            order.append(f"{name}:in")
            time.sleep(0.05)
            order.append(f"{name}:out")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # 任意时刻只有一个线程在临界区内：in/out 严格成对相邻
    for i in range(0, len(order), 2):
        assert order[i].endswith(":in") and order[i + 1] == order[i].replace(":in", ":out")
