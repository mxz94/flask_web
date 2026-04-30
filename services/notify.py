import json

import requests


def ding(message):
    payload = {
        "msgtype": "text",
        "text": {
            "content": f"{message}",
        },
    }
    try:
        headers = {"Content-Type": "application/json"}
        response = requests.post(
            "https://oapi.dingtalk.com/robot/send?access_token=5575d8a5ffffdbc9ad5cd470e733911aece1d8c740a12031d1e96625d210e3ce",
            data=json.dumps(payload),
            headers=headers,
            timeout=10,
            proxies={"http": None, "https": None},
        )
        if response.status_code != 200:
            print(f"发送钉钉通知失败: {response.text}")
    except Exception as e:
        print(f"发送钉钉通知出错: {e}")
