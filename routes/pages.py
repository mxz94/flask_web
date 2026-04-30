from flask import Blueprint, render_template, send_from_directory

from gallery_utils import gallery_main


pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/")
def home():
    return render_template("index.html")


@pages_bp.route("/gallery")
def gallery():
    gallery_main()
    return {"msg": "success"}, 200


@pages_bp.route("/<path:path>")
def serve_static(path):
    try:
        return send_from_directory("./templates", path)
    except Exception as e:
        print(f"静态文件访问错误: {str(e)}")
        return str(e), 404
