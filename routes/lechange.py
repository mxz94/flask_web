from flask import Blueprint, jsonify, request

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
