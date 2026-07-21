import os
from flask import Flask

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=os.path.join(_PROJECT_ROOT, "templates"),
        static_folder=os.path.join(_PROJECT_ROOT, "static"),
    )
    app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200 MB

    from .routes import main_bp
    app.register_blueprint(main_bp)

    from core.jobs import start_cleanup_thread
    start_cleanup_thread()

    return app
