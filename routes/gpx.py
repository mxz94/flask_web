import io
import os
import tempfile

import gpxpy
from flask import Blueprint, request, send_file

from services.gpx_converter import gpx_to_fit


gpx_bp = Blueprint("gpx", __name__)


@gpx_bp.route("/convert", methods=["POST"])
def convert_gpx_to_fit():
    temp_fit_path = None
    try:
        if "gpxFile" not in request.files:
            return "没有文件", 400

        gpx_file = request.files["gpxFile"]
        if gpx_file.filename == "":
            return "没有选择文件", 400

        gpx = gpxpy.parse(gpx_file)
        temp_fit_path = tempfile.mktemp(suffix=".fit")

        fit_file = gpx_to_fit(gpx)
        fit_file.to_file(temp_fit_path)

        with open(temp_fit_path, "rb") as f:
            fit_data = f.read()

        if os.path.exists(temp_fit_path):
            os.remove(temp_fit_path)

        return send_file(
            io.BytesIO(fit_data),
            as_attachment=True,
            download_name=gpx_file.filename.replace(".gpx", ".fit"),
            mimetype="application/octet-stream",
        )

    except Exception as e:
        print(f"转换错误: {str(e)}")
        if temp_fit_path and os.path.exists(temp_fit_path):
            os.remove(temp_fit_path)
        return {"error": str(e)}, 500
