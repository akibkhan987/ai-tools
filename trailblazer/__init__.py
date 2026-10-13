"""TrailBlazer API - application factory."""
from flask import Flask
from pymongo import MongoClient

from .config import Config
from .db import ensure_indexes
from .utils import ApiJSONProvider, register_error_handlers


def create_app(db=None, config_overrides=None):
    """Build and configure the Flask application.

    `db` lets the tests inject an alternative database (e.g. mongomock);
    in normal use a real MongoDB connection is created from the config.
    """
    app = Flask(__name__)
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)

    app.json_provider_class = ApiJSONProvider
    app.json = ApiJSONProvider(app)

    if db is None:
        client = MongoClient(app.config["MONGO_URI"], tz_aware=True)
        db = client[app.config["MONGO_DB"]]
    app.extensions["mongo_db"] = db
    ensure_indexes(db)

    from .blueprints.auth.auth import auth_bp
    from .blueprints.trails.trails import trails_bp
    from .blueprints.reviews.reviews import reviews_bp
    from .blueprints.pois.pois import pois_bp
    from .blueprints.users.users import users_bp
    from .blueprints.stats.stats import stats_bp

    for bp in (auth_bp, trails_bp, reviews_bp, pois_bp, users_bp, stats_bp):
        app.register_blueprint(bp, url_prefix="/api/v1.0")

    register_error_handlers(app)
    return app
