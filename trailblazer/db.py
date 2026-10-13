"""Database access helpers and index definitions."""
from flask import current_app
from pymongo import ASCENDING, DESCENDING, GEOSPHERE


def get_db():
    return current_app.extensions["mongo_db"]


def trails():
    return get_db()["trails"]


def users():
    return get_db()["users"]


def blacklist():
    return get_db()["blacklist"]


def ensure_indexes(db):
    """Create the indexes the API relies on. Safe to call repeatedly."""
    # 2dsphere index is required by $near / $geoNear queries on trailheads
    db.trails.create_index([("location", GEOSPHERE)], name="location_2dsphere")
    db.trails.create_index([("region", ASCENDING), ("difficulty", ASCENDING)], name="region_difficulty")
    db.trails.create_index([("avg_rating", DESCENDING)], name="avg_rating_desc")
    db.users.create_index("username", unique=True, name="username_unique")
    db.users.create_index("email", unique=True, name="email_unique")
    # TTL index: MongoDB deletes revoked tokens automatically once they expire
    db.blacklist.create_index("expires_at", expireAfterSeconds=0, name="expires_ttl")
    db.blacklist.create_index("jti", unique=True, name="jti_unique")
