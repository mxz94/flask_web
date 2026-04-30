import logging
import os

from flask import Blueprint, jsonify, send_from_directory

from services.notify import ding
from triggered_record import RecordingManager
from upload import start_async_upload


recordings_bp = Blueprint("recordings", __name__)

RECORDINGS_DIR = "/www/wwwroot/malanxi/index/lc/records"
recorder = RecordingManager()


@recordings_bp.route("/recordings/dates", methods=["GET"])
def list_recording_dates():
    if not os.path.exists(RECORDINGS_DIR):
        return jsonify([])

    dates = [d for d in os.listdir(RECORDINGS_DIR) if os.path.isdir(os.path.join(RECORDINGS_DIR, d))]
    dates.sort(reverse=True)
    return jsonify(dates)


@recordings_bp.route("/recordings/files/<date_str>", methods=["GET"])
def list_recording_files(date_str):
    date_path = os.path.join(RECORDINGS_DIR, date_str)
    if not os.path.exists(date_path):
        return jsonify([])

    files = [f for f in os.listdir(date_path) if f.endswith(".mp4")]
    files.sort(reverse=True)

    result = []
    for f in files:
        result.append({
            "name": f,
            "url": f"/api/recordings/{date_str}/{f}",
            "size": os.path.getsize(os.path.join(date_path, f)),
        })
    return jsonify(result)


@recordings_bp.route("/recordings/<path:filename>")
def serve_recording(filename):
    return send_from_directory(RECORDINGS_DIR, filename)


@recordings_bp.route("/upload/today", methods=["POST", "GET"])
def trigger_upload_today():
    success, result = start_async_upload(RECORDINGS_DIR)

    if not success:
        return jsonify({"code": 1, "msg": result}), 404

    return jsonify({
        "code": 0,
        "msg": "上传任务已在后台启动，请稍后在云盘查看",
        "date": result,
    })


@recordings_bp.route("/lcnotice", methods=["POST", "GET"])
def lcnotice():
    logging.info("收到回调消息")
    duration = recorder.config.get("trigger_duration_mins", 2)
    ding("检测到移动" + str(duration))
    recorder.trigger(duration_mins=duration)
    return jsonify({
        "code": 0,
        "msg": "kan",
        "date": {},
    })
