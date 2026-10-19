from flask import Flask

from . import config, db


def create_app():
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config["MAX_CONTENT_LENGTH"] = (config.MAX_UPLOAD_MB + 1) * 1024 * 1024
    app.json.sort_keys = False
    from .api import bp
    app.register_blueprint(bp)
    with app.app_context():
        db.connect()

    @app.after_request
    def _headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        if resp.mimetype in ("text/html", "application/javascript", "text/css"):
            resp.headers["Cache-Control"] = "no-cache"
        return resp

    return app
