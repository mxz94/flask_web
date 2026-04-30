import json
import os
import time

from lechange_api import LechangeClient


APP_ID = os.getenv("LECHANGE_APP_ID", "lc023b439a8a7c4b0b")
APP_SECRET = os.getenv("LECHANGE_APP_SECRET", "2575c4063864488ca49d114fa7cbc2")
CONFIG_FILE = "config.json"

client = LechangeClient(APP_ID, APP_SECRET)
cache = {
    "access_token": None,
    "expires_at": 0,
}


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_cached_access_token():
    now = int(time.time())
    if cache["access_token"] and cache["expires_at"] - now >= 300:
        return cache["access_token"]

    token_info = client.get_access_token()
    if not token_info or token_info.get("result", {}).get("code") != "0":
        return None

    data = token_info["result"]["data"]
    cache["access_token"] = data["accessToken"]
    cache["expires_at"] = now + data.get("expire", 86400)
    return cache["access_token"]


def take_device_snapshot(device_id=None, channel_id="0"):
    config = load_config()
    device_id = device_id or config.get("device_id")
    channel_id = str(channel_id or "0")

    if not device_id:
        return False, {"code": "1", "msg": "deviceId is required"}

    access_token = get_cached_access_token()
    if not access_token:
        return False, {"code": "1", "msg": "Failed to get access token"}

    snap_info = client.set_device_snap_enhanced(access_token, device_id, channel_id)
    if not snap_info:
        return False, {"code": "1", "msg": "Failed to request snapshot"}

    result = snap_info.get("result", {})
    return result.get("code") == "0", snap_info
