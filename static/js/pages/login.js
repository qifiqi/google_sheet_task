// 登录页脚本（F5 de-jinja，03 §3 #5）：原服务端注入 loginNextUrl value={{ next_url }}
// 改为运行时从 ?next= 读取；该 hidden input 的消费方 template-auth.js 不变。
document.getElementById('loginNextUrl').value = new URLSearchParams(location.search).get('next') || '';
