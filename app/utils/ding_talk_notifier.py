from datetime import datetime
import requests
import time
import hmac
import hashlib
import base64
import urllib.parse

# from app.utils.logger import get_logger


# logger = get_logger(__name__)
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DingTalkNotifier:
    """
    钉钉机器人通知类
    用于发送消息到钉钉群机器人
    {
        "msgtype": "text", // 消息类型，可为 text、link、markdown、actionCard、feedCard
        "text": {
            "content": "这是一条文本消息内容"
        },
        "link": {
            "messageUrl": "https://www.example.com", // 跳转链接
            "picUrl": "https://example.com/image.png", // 图片链接
            "text": "这是一条链接消息内容", // 消息内容
            "title": "链接消息标题" // 消息标题
        },
        "markdown": {
            "title": "Markdown消息标题",
            "text": "#### 这是Markdown消息内容 \n ![图片](https://example.com/image.png)"
        },
        "actionCard": {
            "title": "ActionCard消息标题",
            "text": "#### 这是ActionCard内容 \n ![图片](https://example.com/image.png)",
            "btnOrientation": "0", // 0-按钮竖直排列，1-按钮横向排列
            "singleTitle": "阅读全文", // 单个按钮标题
            "singleURL": "https://www.example.com", // 单个按钮跳转链接
            "btns": [
            {
                "title": "按钮1",
                "actionURL": "https://www.example.com/btn1"
            },
            {
                "title": "按钮2",
                "actionURL": "https://www.example.com/btn2"
            }
            ]
        },
        "feedCard": {
            "links": [
            {
                "title": "FeedCard标题1",
                "messageURL": "https://www.example.com/1",
                "picURL": "https://example.com/image1.png"
            },
            {
                "title": "FeedCard标题2",
                "messageURL": "https://www.example.com/2",
                "picURL": "https://example.com/image2.png"
            }
            ]
        },
        "at": {
            "isAtAll": false, // 是否@所有人
            "atUserIds": ["user001", "user002"], // 被@的用户ID列表
            "atMobiles": ["15xxx", "18xxx"] // 被@的手机号列表
        }
        }
        
    """

    def __init__(self, access_token, secret):
        """
        初始化钉钉通知器

        Args:
            access_token (str): 钉钉机器人的access_token
            secret (str): 钉钉机器人的签名密钥
        """
        self.access_token = access_token
        self.secret = secret
        self.base_url = 'https://oapi.dingtalk.com/robot/send'

    def _generate_signature(self):
        """
        生成签名用于安全验证

        Returns:
            tuple: (timestamp, sign) 时间戳和签名
        """
        timestamp = str(round(time.time() * 1000))
        secret_enc = self.secret.encode('utf-8')
        string_to_sign = '{}\n{}'.format(timestamp, self.secret)
        string_to_sign_enc = string_to_sign.encode('utf-8')
        hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        return timestamp, sign

    def error_google_task_templates(self,task_id,error_msg,url):
        return {
            "msgtype": "actionCard", 
            "actionCard": {
                "title": "🚨 告警：任务执行异常",
                "text": f"""## 🚨 任务执行告警
                        
        **任务ID**: {task_id}  
        **告警时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
        **异常信息**: {error_msg}
                        
        > 请及时处理！""",
                "btnOrientation": "0", 
                "btns": [
                    {
                        "title": "🔍 查看报错详情",
                        "actionURL": url
                    }
                ]
            },
            "at": {
                "isAtAll": False,
            }
        }

    def google_task_ok_templates(self,task_id,msg,url):
        
        return {
            "msgtype": "actionCard", 
            "actionCard": {
                "title": "🎉 任务完成通知",
                "text": f"""## 任务执行完成
                        
        **任务ID**: {task_id}  
        **完成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
        **执行结果**: {msg}
                        
        ---""",
                "btnOrientation": "0",
                "btns": [
                    {
                        "title": "📎 查看详情",
                        "actionURL": url
                    }
                ]
            },
            "at": {
                "isAtAll": False,
            }
        }


    def send_message(self,data):
        """
        发送消息到钉钉

        Args:
            :param data:
        Returns:
            dict: 响应结果
        """
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

# 使用示例
if __name__ == '__main__':
    # 初始化钉钉通知器
    notifier = DingTalkNotifier(
        access_token='a0fe95aac4a01a4c6826caf95087698baa6473804ee81dc2afaf4458e770eccc',
        secret='SEC3309a1318e963385c7a805d2530cb7d6f2128fe4c9f26673cbad7f599927a498'
    )


    # 发送消息
    result = notifier.send_message({
        "msgtype": "text", 
        "text": {
            "content": "任务完成测试 这是一条文本消息内容"
        },
        "at": {
            "atMobiles": ["13823582442"] 
        }
        }
        )
    print(result)

