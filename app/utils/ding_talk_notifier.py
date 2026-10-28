from datetime import datetime
import base64
import hashlib
import hmac
import time
import urllib.parse
import re

import requests
from flask import current_app, has_app_context

from app.repositories import task_repository
from app.utils.logger import get_logger


logger = get_logger(__name__)


# webhook URL 查询串里的凭据参数，异常消息落日志前打码
_CREDENTIAL_URL_PARAMS = re.compile(r"(access_token|sign)=[^&\s'\"]+", re.IGNORECASE)


def _redact_credentials(text: str) -> str:
    """打码文本中内嵌的钉钉 webhook 凭据（access_token/sign）。"""
    return _CREDENTIAL_URL_PARAMS.sub(lambda m: m.group(1) + "=***", str(text or ""))


def resolve_external_base_url(config) -> str:
    """解析外部通知展示链接使用的对外访问基地址。

    优先级：``DING_TALK_DETAIL_BASE_URL`` > ``PUBLIC_BASE_URL`` > ``BASE_URL``，
    末尾斜杠统一去掉。该地址只用于生成钉钉 markdown 链接（展示），服务端不会
    请求它，因此不涉及出站请求与 SSRF；但非 http/https 或缺主机的值会被拒绝，
    避免把非法 scheme（如 ``javascript:``）写进通知正文。
    """
    if config is None:
        return ''
    value = (
        config.get('DING_TALK_DETAIL_BASE_URL')
        or config.get('PUBLIC_BASE_URL')
        or config.get('BASE_URL')
        or ''
    )
    text = str(value).strip().rstrip('/')
    if not text:
        return ''
    parsed = urllib.parse.urlsplit(text)
    if parsed.scheme.lower() not in ('http', 'https') or not parsed.netloc:
        logger.warning("外部通知基地址不是合法的 http(s) 地址，已忽略: %r", value)
        return ''
    return text


def get_external_base_url() -> str:
    """当前应用上下文的对外访问基地址；无上下文时返回空串。"""
    if not has_app_context():
        return ''
    return resolve_external_base_url(current_app.config)


class DingTalkNotifier:
    """钉钉机器人通知器。

    @ 手机号机制已移除（2026-10-02，db-to-http 迁移）：值班/创建人手机号
    原读本地 User 表，纯 http 部署下该表不再维护，收件人恒失效。
    """

    NOTIFY_KEYWORDS = {
        "error": "告警",
        "success": "任务完成",
    }

    def __init__(self, access_token, secret):
        self.access_token = access_token
        self.secret = secret
        self.base_url = 'https://oapi.dingtalk.com/robot/send'

    def _generate_signature(self):
        timestamp = str(round(time.time() * 1000))
        secret_enc = self.secret.encode('utf-8')
        string_to_sign = f'{timestamp}\n{self.secret}'
        string_to_sign_enc = string_to_sign.encode('utf-8')
        hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        return timestamp, sign

    def _task_detail_url(self, task_id, detail_url=None):
        if detail_url:
            return detail_url
        if not has_app_context():
            return ''
        base_url = self._get_external_base_url()
        if not base_url or not task_id:
            return ''
        return f"{base_url}/google-sheet/detail?task_id={task_id}"

    def _get_external_base_url(self):
        """获取钉钉等外部通知场景使用的对外访问基地址。"""
        if not has_app_context():
            return ''

        return get_external_base_url()

    def _build_markdown_text(
        self,
        keyword,
        fields,
        summary=None,
        detail_url=None,
    ):
        """构建钉钉 markdown 正文。

        @ 手机号机制已移除（2026-10-02，db-to-http 迁移）：值班/创建人手机号
        原读本地 User 表，纯 http 部署下该表不再维护。后续如需恢复 @ 人，
        从主 Web 接口取值班名单（见 docs/design/db-to-http-migration/ §8）。
        """
        lines = [f"### {keyword}", ""]
        for label, value in fields:
            normalized_value = str(value or "").strip() or "-"
            lines.append(f"- **{label}**：{normalized_value}")

        summary_text = str(summary or "").strip()
        if summary_text:
            lines.extend([
                "",
                "> 摘要",
                f"> {summary_text}",
            ])

        if detail_url:
            lines.extend([
                "",
                f"[查看详情]({detail_url})",
            ])

        return "\n".join(lines)

    def _creator_display_name(self, task):
        """创建人显示名：db 后端为本地用户名；http 后端 RemoteRecord 无
        created_by 关系（getattr 默认值兼容），退化为 created_by_user_id。"""
        creator = getattr(task, "created_by", None)
        if creator is not None and getattr(creator, "username", None):
            return creator.username
        return str(getattr(task, "created_by_user_id", None) or "").strip() or "系统/未知"

    def send_task_notification(self, task_id, notify_type='error', summary=None, detail_url=None):
        task_id = str(task_id or '').strip()
        task = task_repository.get_entity(task_id) if task_id else None
        keyword = self.NOTIFY_KEYWORDS.get(notify_type, "通知")
        title = f"{keyword} - 任务执行失败" if notify_type == 'error' else f"{keyword} - 任务执行完成"
        target_url = self._task_detail_url(task_id, detail_url)

        if not task:
            fallback_summary = str(summary or '任务通知').strip()
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "title": title,
                    "text": self._build_markdown_text(
                        keyword,
                        [
                            ("任务状态", title),
                            ("任务ID", task_id or "未知"),
                            ("通知时间", datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                        ],
                        summary=fallback_summary,
                        detail_url=target_url,
                    ),
                },
                "at": {"isAtAll": False},
            }
            return self.send_message(payload)

        summary_text = str(summary or '').strip()
        if not summary_text:
            summary_text = task.error_message if notify_type == 'error' else '任务执行完成'

        status_label = '执行成功' if notify_type == 'success' else '执行失败'
        creator_name = self._creator_display_name(task)
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": self._build_markdown_text(
                    keyword,
                    [
                        ("任务状态", status_label),
                        ("任务名称", task.name),
                        ("任务ID", task.id),
                        ("任务类型", task.task_type),
                        ("创建人", creator_name),
                        ("通知时间", datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                    ],
                    summary=summary_text,
                    detail_url=target_url,
                ),
            },
            "at": {"isAtAll": False},
        }
        logger.info(
            "准备发送钉钉通知: task_id=%s notify_type=%s creator=%s",
            task_id or 'unknown',
            notify_type,
            creator_name,
        )
        return self.send_message(payload)

    def send_message(self, data):
        try:
            if not self.access_token or not self.secret:
                logger.error("钉钉通知发送失败: access_token 或 secret 未配置")
                return {"error": "ding_talk_not_configured"}

            timestamp, sign = self._generate_signature()
            url = f'{self.base_url}?access_token={self.access_token}&timestamp={timestamp}&sign={sign}'
            response = requests.post(url, json=data, timeout=10)
            response.raise_for_status()
            result = response.json()

            if result.get("errcode") not in (None, 0):
                logger.error("钉钉通知发送失败: %s", _redact_credentials(str(result)))
            else:
                logger.info("钉钉通知发送成功")

            return result
        except Exception as e:
            logger.error("发送钉钉消息失败: %s", _redact_credentials(str(e)), exc_info=True)
            return {"error": str(e)}
