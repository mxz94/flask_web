import logging

from flask import Flask
from flask_cors import CORS
from pillow_heif import register_heif_opener

from routes import register_blueprints


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("triggered_record.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

register_heif_opener()


def create_app():
    app = Flask(__name__, static_url_path="", static_folder="./templates")
    CORS(app, resources={r"/*": {"origins": "*"}})
    register_blueprints(app)
    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
