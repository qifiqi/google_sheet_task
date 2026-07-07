#!/usr/bin/env python3
import argparse
import dingtalk_stream
import json
import time
import re
import random
import requests

class MyEventHandler(dingtalk_stream.EventHandler):
    def __init__(self, client_id=None, client_secret=None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
        self.token_expire_time = 0
    
    async def process(self, event: dingtalk_stream.EventMessage):
        try:
            # 打印事件类型用于调试
            print(f"\n{'='*50}")
            print(f"收到事件类型: {event.headers.event_type}")
            
            # 判断是否是机器人消息（从data中判断）
            msg_data = event.data
            if 'text' in msg_data and 'conversationId' in msg_data:
                # 有text字段且有会话ID，说明是消息
                return await self.handle_bot_message(event)
            else:
                print("不是消息事件，忽略")
                return dingtalk_stream.AckMessage.STATUS_OK, 'OK'
            
        except Exception as e:
            print(f"处理消息时出错: {e}")
            import traceback
            traceback.print_exc()
        
        return dingtalk_stream.AckMessage.STATUS_OK, 'OK'
    
    async def handle_bot_message(self, event):
        """处理机器人消息"""
        msg_data = event.data
        
        # 提取消息信息
        text_content = msg_data.get('text', {}).get('content', '').strip()  # 去除首尾空格
        sender_id = msg_data.get('senderId', '')
        sender_nick = msg_data.get('senderNick', '')
        conversation_id = msg_data.get('conversationId', '')
        conversation_type = msg_data.get('conversationType', '')  # 1:单聊, 2:群聊
        msg_id = msg_data.get('msgId', '')
        at_users = msg_data.get('atUsers', [])
        session_webhook = msg_data.get('sessionWebhook', '')  # 重要：直接回复的webhook
        
        print(f"📨 收到群消息:")
        print(f"  发送者: {sender_nick}({sender_id})")
        print(f"  会话ID: {conversation_id}")
        print(f"  消息内容: '{text_content}'")
        print(f"  会话类型: {'群聊' if conversation_type == '2' else '单聊'}")
        print(f"  Webhook: {session_webhook[:50]}...")
        
        # 如果消息为空，不处理
        if not text_content:
            print("⏭️ 消息内容为空，跳过处理")
            return dingtalk_stream.AckMessage.STATUS_OK, 'OK'
        
        # 处理消息并获取回复
        reply_text = self.process_message(text_content, sender_nick)
        
        if reply_text:
            print(f"🤖 准备回复: {reply_text}")
            # 使用session_webhook直接回复
            await self.send_reply_via_webhook(session_webhook, reply_text)
        
        return dingtalk_stream.AckMessage.STATUS_OK, 'OK'
    
    def process_message(self, text, sender_nick):
        """处理消息内容，返回回复文本"""
        # 去除@机器人的前缀（如果存在）
        text = re.sub(r'@[\u4e00-\u9fa5a-zA-Z0-9_]+', '', text).strip()
        
        print(f"处理后消息: '{text}'")
        
        # 1. 功能菜单
        if text in ['帮助', 'help', '功能', '菜单', '?', '？']:
            return f"""📋 功能菜单 @{sender_nick}：

1️⃣ "你好" - 打招呼
2️⃣ "时间" - 查看当前时间  
3️⃣ "天气" - 查询天气
4️⃣ "笑话" - 讲个笑话
5️⃣ "日期" - 显示今天日期
6️⃣ "感谢" - 表达感谢
7️⃣ "再见" - 道别
8️⃣ "帮助" - 显示此菜单

💡 直接输入关键词即可使用"""
        
        # 2. 打招呼
        if text in ['你好', '您好', 'hi', 'hello', 'hey', '大家好']:
            greetings = [
                f"你好 {sender_nick}！👋",
                f"Hi {sender_nick}！很高兴见到你 😊",
                f"你好呀 {sender_nick}！有什么需要帮助的吗？",
                f"嗨 {sender_nick}！欢迎来到群里 🎉"
            ]
            return f"{random.choice(greetings)}\n回复'帮助'查看功能菜单"
        
        # 3. 时间
        if text in ['时间', '几点', '现在几点', '当前时间']:
            current_time = time.strftime("%Y年%m月%d日 %H:%M:%S")
            return f"🕐 {sender_nick}，当前时间是：{current_time}"
        
        # 4. 日期
        if text in ['日期', '今天', '几号', '今天几号']:
            current_date = time.strftime("%Y年%m月%d日")
            weekday = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][time.localtime().tm_wday]
            return f"📅 {sender_nick}，今天是 {current_date} {weekday}"
        
        # 5. 天气
        if text in ['天气', '今天天气', '天气预报']:
            return f"""🌤️ {sender_nick}，天气查询提醒：
由于需要实时数据，建议您：
• 查看手机天气APP
• 访问 https://weather.com
• 搜索"城市名+天气"

当前为示例回复，实际使用可接入天气API"""
        
        # 6. 笑话
        if text in ['笑话', '讲个笑话', '段子', '幽默']:
            jokes = [
                "为什么程序员总是分不清万圣节和圣诞节？\n因为 Oct 31 = Dec 25！🎃",
                "一个SQL语句走进酒吧，看到两张桌子，问：我能JOIN你们吗？🍺",
                "程序员最讨厌的饮料是什么？Java，因为会让人越喝越Coffee！☕",
                "为什么Python程序员喜欢自然语言处理？\n因为处理字符串比处理人际关系简单多了！💻",
                "当你的代码运行一次就成功了，\n那感觉就像是你写了一个bug，但是正好让程序工作了！🐛",
                "什么是程序员最大的谎言？\n'我只要改一行代码就能搞定' 😅",
                "为什么计算机科学家会混淆圣诞节和国庆节？\n因为DEC 25 = OCT 31！🎄"
            ]
            return f"😂 {sender_nick}，来听个笑话：\n\n{random.choice(jokes)}"
        
        # 7. 感谢
        if any(keyword in text for keyword in ['谢谢', '感谢', '多谢', 'thanks', 'thank']):
            thanks = [
                f"不客气 {sender_nick}！很高兴能帮到你 😊",
                f"举手之劳 {sender_nick}！有事随时叫我 👌",
                f"不用谢 {sender_nick}！有需要再找我哦 🌟"
            ]
            return random.choice(thanks)
        
        # 8. 再见
        if text in ['再见', '拜拜', 'bye', 'goodbye', '88']:
            byes = [
                f"再见 {sender_nick}！下次再聊 👋",
                f"拜拜 {sender_nick}！祝你有美好的一天 🌈",
                f"{sender_nick}，后会有期！😄"
            ]
            return random.choice(byes)
        
        # 9. 技术支持类
        if any(keyword in text for keyword in ['问题', '错误', 'bug', '故障', '报错', '失败']):
            return f"""🔧 {sender_nick}，遇到问题了吗？

建议排查步骤：
1️⃣ 查看错误日志详细信息
2️⃣ 检查网络连接状态
3️⃣ 重启服务重试
4️⃣ 确认配置是否正确

如问题持续，请联系技术支持团队。"""
        
        # 10. 默认回复
        if text:
            default_responses = [
                f"收到 {sender_nick} 的消息：\"{text}\" 💬\n\n🤔 我不太明白这个意思，回复'帮助'查看我能做什么",
                f"\"{text}\" 嗯... {sender_nick}，我需要再学习学习 📚\n回复'帮助'看看我有哪些功能",
                f"👋 {sender_nick}，我收到了你的消息！\n不过这个我还不太懂，要不试试'帮助'？"
            ]
            return random.choice(default_responses)
        else:
            return f"@{sender_nick} 收到消息！有什么可以帮你的？回复'帮助'查看功能菜单"
    
    async def send_reply_via_webhook(self, webhook_url, reply_text):
        """使用session_webhook发送消息（推荐方式）"""
        try:
            if not webhook_url:
                print("❌ webhook URL为空，无法发送消息")
                return
            
            headers = {
                "Content-Type": "application/json"
            }
            
            data = {
                "msgtype": "text",
                "text": {
                    "content": reply_text
                }
            }
            
            response = requests.post(webhook_url, headers=headers, json=data)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('errcode') == 0:
                    print(f"✅ 消息发送成功")
                else:
                    print(f"❌ 消息发送失败: {result}")
            else:
                print(f"❌ HTTP请求失败: {response.status_code} - {response.text}")
                
        except Exception as e:
            print(f"❌ 发送消息时出错: {e}")
    
    async def get_access_token(self):
        """获取钉钉access_token"""
        try:
            # 检查token是否过期（提前60秒刷新）
            if self.access_token and time.time() < self.token_expire_time - 60:
                return self.access_token
            
            url = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
            data = {
                "appKey": self.client_id,
                "appSecret": self.client_secret
            }
            response = requests.post(url, json=data)
            if response.status_code == 200:
                result = response.json()
                self.access_token = result.get("accessToken")
                self.token_expire_time = time.time() + result.get("expireIn", 7200)
                print(f"✅ 获取access_token成功")
                return self.access_token
            print(f"❌ 获取access_token失败: {response.text}")
            return None
        except Exception as e:
            print(f"❌ 获取access_token失败: {e}")
            return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--client_id', required=True, help='钉钉应用的Client ID')
    parser.add_argument('--client_secret', required=True, help='钉钉应用的Client Secret')
    args = parser.parse_args()

    # 创建并配置客户端
    credential = dingtalk_stream.Credential(args.client_id, args.client_secret)
    client = dingtalk_stream.DingTalkStreamClient(credential)
    
    # 注册事件处理器
    handler = MyEventHandler(args.client_id, args.client_secret)
    client.register_callback_handler(
        "/v1.0/im/bot/messages/get",
        handler
    )
    
    print("🤖 钉钉群机器人启动成功！")
    print("=" * 50)
    print("📌 功能介绍：")
    print("  💬 在群里 @机器人 即可使用")
    print("  📋 回复'帮助'查看所有功能")
    print("  ⏰ 支持：你好、时间、天气、笑话等")
    print("=" * 50)
    print("等待接收群消息...")
    
    # 启动客户端
    client.start_forever()

if __name__ == '__main__':
    main()