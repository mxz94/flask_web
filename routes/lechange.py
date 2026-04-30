import time
from datetime import datetime

import requests
from flask import Blueprint, Response, jsonify, request

from services.lechange_service import take_device_snapshot


lechange_bp = Blueprint("lechange", __name__)


@lechange_bp.route("/lc/snapshot", methods=["GET", "POST"])
def snapshot():
    data = request.get_json(silent=True) or {}
    device_id = data.get("deviceId") or request.values.get("deviceId")
    channel_id = data.get("channelId") or request.values.get("channelId", "0")

    success, result = take_device_snapshot(device_id=device_id, channel_id=channel_id)
    if not success:
        return jsonify(result), 500

    return jsonify({
        "code": 0,
        "url": result["result"]["data"]["url"],
        "raw": result,
    })


@lechange_bp.route("/lc/snapshot/image", methods=["GET", "POST"])
@lechange_bp.route("/lc/snapshot.jpg", methods=["GET", "POST"])
def snapshot_image():
    data = request.get_json(silent=True) or {}
    device_id = data.get("deviceId") or request.values.get("deviceId")
    channel_id = data.get("channelId") or request.values.get("channelId", "0")

    success, result = take_device_snapshot(device_id=device_id, channel_id=channel_id)
    if not success:
        return jsonify(result), 500

    image_url = result["result"]["data"]["url"]
    last_error = None
    image_response = None
    session = requests.Session()
    session.trust_env = False

    for attempt in range(6):
        try:
            image_response = session.get(image_url, timeout=15)
            image_response.raise_for_status()
            break
        except requests.RequestException as e:
            last_error = e
            if attempt < 5:
                time.sleep(0.8)
    else:
        return jsonify({
            "code": 1,
            "msg": f"Failed to download snapshot image: {last_error}",
            "url": image_url,
        }), 502

    content_type = image_response.headers.get("Content-Type", "image/jpeg")
    response = Response(image_response.content, mimetype=content_type)
    filename = datetime.now().strftime("snapshot_%Y%m%d_%H%M%S.jpg")
    response.headers["Content-Disposition"] = f'inline; filename="{filename}"'
    return response
