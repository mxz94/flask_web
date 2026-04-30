import hashlib
import time
import uuid
import requests
import json

class LechangeClient:
    def __init__(self, app_id, app_secret):
        self.app_id = app_id
        self.app_secret = app_secret
        self.base_url = "https://openapi.lechange.cn/openapi"
        self.session = requests.Session()
        self.session.trust_env = False

    def _generate_sign(self, timestamp, nonce):
        """
        计算签名 sign
        算法: md5(time:{time},nonce:{nonce},appSecret:{appSecret})
        """
        sign_template = f"time:{timestamp},nonce:{nonce},appSecret:{self.app_secret}"
        sign = hashlib.md5(sign_template.encode('utf-8')).hexdigest()
        return sign

    def get_access_token(self):
        """
        获取 accessToken
        接口地址: https://openapi.lechange.cn/openapi/accessToken
        """
        url = f"{self.base_url}/accessToken"
        
        timestamp = int(time.time())
        nonce = str(uuid.uuid4())
        request_id = str(uuid.uuid4())
        
        sign = self._generate_sign(timestamp, nonce)
        
        payload = {
            "system": {
                "ver": "1.0",
                "appId": self.app_id,
                "sign": sign,
                "time": timestamp,
                "nonce": nonce
            },
            "id": request_id,
            "params": {}
        }
        
        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching access token: {e}")
            response = getattr(e, "response", None)
            if response is not None:
                print(f"Response: {response.text}")
            return None

    def get_kit_token(self, access_token, device_id, channel_id, kit_type="0"):
        """
        获取 kitToken
        接口地址: https://openapi.lechange.cn/openapi/getKitToken
        :param access_token: 管理员 accessToken
        :param device_id: 设备序列号
        :param channel_id: 设备通道号
        :param kit_type: 权限类型 (0: 所有权限; 1: 实时预览; 2: 录像回放; 6: 云台转动)
        """
        url = f"{self.base_url}/getKitToken"
        
        timestamp = int(time.time())
        nonce = str(uuid.uuid4())
        request_id = str(uuid.uuid4())
        
        sign = self._generate_sign(timestamp, nonce)
        
        payload = {
            "system": {
                "ver": "1.0",
                "appId": self.app_id,
                "sign": sign,
                "time": timestamp,
                "nonce": nonce
            },
            "id": request_id,
            "params": {
                "token": access_token,
                "deviceId": device_id,
                "channelId": channel_id,
                "type": kit_type
            }
        }
        
        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching kit token: {e}")
            return None

    def get_live_stream_info(self, access_token, device_id, channel_id):
        """
        获取直播流信息 (HLS/RTMP)
        接口地址: https://openapi.lechange.cn/openapi/getLiveStreamInfo
        """
        url = f"{self.base_url}/getLiveStreamInfo"
        
        timestamp = int(time.time())
        nonce = str(uuid.uuid4())
        request_id = str(uuid.uuid4())
        
        sign = self._generate_sign(timestamp, nonce)
        
        payload = {
            "system": {
                "ver": "1.0",
                "appId": self.app_id,
                "sign": sign,
                "time": timestamp,
                "nonce": nonce
            },
            "id": request_id,
            "params": {
                "token": access_token,
                "deviceId": device_id,
                "channelId": channel_id
            }
        }
        
        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching live stream info: {e}")
            return None

    def set_device_snap_enhanced(self, access_token, device_id, channel_id="0"):
        """
        设备抓图升级版
        接口地址: https://openapi.lechange.cn/openapi/setDeviceSnapEnhanced
        """
        url = f"{self.base_url}/setDeviceSnapEnhanced"

        timestamp = int(time.time())
        nonce = str(uuid.uuid4())
        request_id = str(uuid.uuid4())

        sign = self._generate_sign(timestamp, nonce)

        payload = {
            "system": {
                "ver": "1.0",
                "appId": self.app_id,
                "sign": sign,
                "time": timestamp,
                "nonce": nonce
            },
            "id": request_id,
            "params": {
                "token": access_token,
                "deviceId": device_id,
                "channelId": channel_id
            }
        }

        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error taking enhanced snapshot: {e}")
            return None

if __name__ == "__main__":
    # 示例用法
    # 请替换为您在乐橙开放平台申请的 appId 和 appSecret
    APP_ID = "lc023b439a8a7c4b0b"
    APP_SECRET = "2575c4063864488ca49d114fa7cbc2"
    
    client = LechangeClient(APP_ID, APP_SECRET)
    token_info = client.get_access_token()
    
    if token_info and token_info.get("result", {}).get("code") == "0":
        access_token = token_info["result"]["data"]["accessToken"]
        print(f"Successfully retrieved access token: {access_token}")
        
        # 示例: 获取 kitToken (请替换为真实的 deviceId 和 channelId)
        device_id = "9A024A3PCG3F942"
        channel_id = "0"
        kit_info = client.get_kit_token(access_token, device_id, channel_id)
        print("Kit Token Info:")
        print(json.dumps(kit_info, indent=4, ensure_ascii=False))
    else:
        print("Failed to retrieve token info.")
        print(json.dumps(token_info, indent=4, ensure_ascii=False))
