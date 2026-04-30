from datetime import datetime
import base64
import hashlib
import hmac
import time
import urllib.parse

import requests
from flask import current_app, has_app_context

from app.models import Task, User
from app.utils.logger import get_logger


logger = get_logger(__name__)


class DingTalkNotifier:
    """钉钉机器人通知器。"""

    DEV_ROLE_CODES = {"developer"}

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

    def _normalize_mobile(self, value):
        mobile = str(value or '').strip()
        return mobile or None

    def _mask_mobile(self, mobile):
        raw = self._normalize_mobile(mobile)
        if not raw:
            return None
        if len(raw) <= 7:
            return raw
        return f"{raw[:3]}****{raw[-4:]}"

    def _task_detail_url(self, task_id, detail_url=None):
        if detail_url:
            return detail_url
        if not has_app_context():
            return ''
        base_url = (current_app.config.get('BASE_URL') or '').rstrip('/')
        if not base_url or not task_id:
            return ''
        return f"{base_url}/google-sheet/detail?task_id={task_id}"

    def _collect_oncall_developer_mobiles(self):
        mobiles = set()
        users = User.query.filter_by(is_active=True, is_alert_oncall=True).all()
        for user in users:
            role_codes = {str(role.code or '').strip().lower() for role in user.roles}
            if role_codes & self.DEV_ROLE_CODES:
                mobile = self._normalize_mobile(user.mobile)
                if mobile:
                    mobiles.add(mobile)
        return mobiles

    def _collect_at_mobiles(self, task, notify_type):
        mobiles = set()
        if task and task.created_by:
            creator_mobile = self._normalize_mobile(task.created_by.mobile)
            if creator_mobile:
                mobiles.add(creator_mobile)

        if notify_type == 'error':
            mobiles.update(self._collect_oncall_developer_mobiles())

        return sorted(mobiles)

    def send_task_notification(self, task_id, notify_type='error', summary=None, detail_url=None):
        task_id = str(task_id or '').strip()
        task = Task.query.get(task_id) if task_id else None
        title = '任务执行失败' if notify_type == 'error' else '任务执行完成'
        target_url = self._task_detail_url(task_id, detail_url)

        if not task:
            fallback_summary = str(summary or '任务通知').strip()
            payload = {
                "msgtype": "actionCard",
                "actionCard": {
                    "title": title,
                    "text": "\n".join([
                        f"任务状态：{title}",
                        f"任务ID：{task_id or '未知'}",
                        f"通知时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                        f"摘要：{fallback_summary}",
                    ]),
                    "btnOrientation": "0",
                    "singleTitle": "查看详情",
                    "singleURL": target_url,
                },
                "at": {"isAtAll": False},
            }
            return self.send_message(payload)

        summary_text = str(summary or '').strip()
        if not summary_text:
            summary_text = task.error_message if notify_type == 'error' else '任务执行完成'

        status_label = '执行成功' if notify_type == 'success' else '执行失败'
        creator_name = task.created_by.username if task.created_by else '系统/未知'
        payload = {
            "msgtype": "actionCard",
            "actionCard": {
                "title": title,
                "text": "\n".join([
                    f"任务状态：{status_label}",
                    f"任务名称：{task.name}",
                    f"任务ID：{task.id}",
                    f"任务类型：{task.task_type}",
                    f"创建人：{creator_name}",
                    f"通知时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    f"摘要：{summary_text}",
                ]),
                "btnOrientation": "0",
                "singleTitle": "查看详情",
                "singleURL": target_url,
            },
            "at": {"isAtAll": False},
        }
        mobiles = self._collect_at_mobiles(task, notify_type)
        logger.info(
            "准备发送钉钉通知: task_id=%s notify_type=%s creator=%s creator_mobile=%s at_mobiles=%s",
            task_id or 'unknown',
            notify_type,
            task.created_by.username if task and task.created_by else None,
            self._mask_mobile(task.created_by.mobile if task and task.created_by else None),
            [self._mask_mobile(mobile) for mobile in mobiles],
        )
        if mobiles:
            payload["at"]["atMobiles"] = mobiles
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
                logger.error(f"钉钉通知发送失败: {result}")
            else:
                logger.info("钉钉通知发送成功")

            return result
        except Exception as e:
            logger.error(f"发送钉钉消息失败: {str(e)}", exc_info=True)
            return {"error": str(e)}
