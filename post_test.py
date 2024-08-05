import requests
from datetime import datetime

# 要发送的数据，包含命令和参数
data = {
    'text': 'https://www.canva.cn'
}

# FastAPI 应用的 URL 和端口
url = 'http://127.0.0.1:8080/receive-data'

# 发送 POST 请求
response = requests.post(url, json=data)

# 检查响应状态码
if response.status_code == 200:
    print('数据发送成功，服务器响应：')
    print(response.json())
else:
    print('数据发送失败，状态码：', response.status_code)
