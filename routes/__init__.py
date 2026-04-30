from .pages import pages_bp
from .exif import exif_bp
from .gpx import gpx_bp
from .lechange import lechange_bp
from .plog import plog_bp
from .recordings import recordings_bp


def register_blueprints(app):
    app.register_blueprint(pages_bp)
    app.register_blueprint(exif_bp)
    app.register_blueprint(gpx_bp)
    app.register_blueprint(lechange_bp)
    app.register_blueprint(plog_bp)
    app.register_blueprint(recordings_bp)
