import json
import os

from flask import Blueprint, jsonify, request
from PIL import Image

from services.plog_upload import compress_image, post_to_plog, upload_image


plog_bp = Blueprint("plog", __name__)


@plog_bp.route("/upload", methods=["POST"])
def convert_heic_to_jpg_and_upload():
    title = request.form.get("title", "")
    pwd = request.form.get("pwd", "")
    files = request.files.getlist("files")
    upload_results = []
    if pwd != "qq67607301":
        return jsonify({"message": "pwd is error"})

    for file in files:
        file.save(file.filename)
        if file.filename.lower().endswith(".heic"):
            img = Image.open(file)
            exif = img.info.get("exif")
            icc_profile = img.info.get("icc_profile")
            output_file = os.path.splitext(file.filename)[0] + ".jpg"
            img.save(output_file, exif=exif, icc_profile=icc_profile)

            compress_image(output_file)
            upload_url = upload_image(output_file, None)
            os.remove(output_file)
        else:
            compress_image(file.filename)
            upload_url = upload_image(file.filename, None)
        os.remove(file.filename)

        data = post_to_plog(title, upload_url, "1")
        print(data)
        upload_results.append({
            "filename": file.filename,
            "upload_url": upload_url,
            "data": json.dumps(data, ensure_ascii=False, indent=4),
        })

    return jsonify({"message": "All files processed", "results": str(upload_results)})
