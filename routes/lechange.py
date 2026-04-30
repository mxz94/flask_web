import time
from datetime import datetime

import requests
from flask import Blueprint, Response, jsonify, request

from services.lechange_service import take_device_snapshot
from services.exif_writer import write_bytes_exif


lechange_bp = Blueprint("lechange", __name__)

DEFAULT_EXIF = {
    "latitude": "34;35;44.11999999999955139",
    "longitude": "112;30;33.7299999999814304",
    "altitude": "148.512918994413411",
    "make": "Lechange",
    "model": "9A024A3PCG3F942",
}


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
    image_content = image_response.content

    try:
        image_content = write_bytes_exif(
            image_content,
            latitude=request.values.get("latitude", DEFAULT_EXIF["latitude"]),
            longitude=request.values.get("longitude", DEFAULT_EXIF["longitude"]),
            altitude=request.values.get("altitude", DEFAULT_EXIF["altitude"]),
            taken_at=request.values.get("datetime"),
            make=request.values.get("make", DEFAULT_EXIF["make"]),
            model=request.values.get("model", DEFAULT_EXIF["model"]),
        ).getvalue()
        content_type = "image/jpeg"
    except Exception as e:
        return jsonify({
            "code": 1,
            "msg": f"Failed to write snapshot exif: {e}",
        }), 500

    response = Response(image_content, mimetype=content_type)
    filename = datetime.now().strftime("snapshot_%Y%m%d_%H%M%S.jpg")
    response.headers["Content-Disposition"] = f'inline; filename="{filename}"'
    return response
