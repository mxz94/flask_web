from datetime import datetime

from flask import Blueprint, Response, jsonify, request

from services.exif_writer import write_image_exif


exif_bp = Blueprint("exif", __name__)


def _form_value(*names, default=None):
    for name in names:
        value = request.form.get(name)
        if value not in (None, ""):
            return value
    return default


@exif_bp.route("/tools/exif", methods=["POST"])
def add_exif():
    image_file = request.files.get("file")
    if not image_file:
        return jsonify({"code": 1, "msg": "file is required"}), 400

    latitude = _form_value("latitude", "lat", "纬度")
    longitude = _form_value("longitude", "lng", "lon", "经度")
    if not latitude or not longitude:
        return jsonify({"code": 1, "msg": "latitude and longitude are required"}), 400

    try:
        output = write_image_exif(
            image_file,
            latitude=latitude,
            longitude=longitude,
            altitude=_form_value("altitude", "alt", "高度"),
            taken_at=_form_value("datetime", "time", "时间"),
            make=_form_value("make", "照相机制造商", default="Lechange"),
            model=_form_value("model", "照相机型号", default="9A024A3PCG3F942"),
        )
    except Exception as e:
        return jsonify({"code": 1, "msg": f"failed to write exif: {e}"}), 500

    filename = datetime.now().strftime("exif_%Y%m%d_%H%M%S.jpg")
    response = Response(output.getvalue(), mimetype="image/jpeg")
    response.headers["Content-Disposition"] = f'inline; filename="{filename}"'
    return response
