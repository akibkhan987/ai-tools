"""Load the TrailBlazer dataset into MongoDB.

Usage (from the project root):
    python -m seed.seed_db            # drops and recreates the trails/users/blacklist collections
"""
import os
import sys

from pymongo import MongoClient

from trailblazer.db import ensure_indexes

from .build_dataset import ADMIN_PASSWORD, DEMO_PASSWORD, build


def seed(db):
    data = build()
    for name in ("trails", "users", "blacklist"):
        db[name].drop()
    db.users.insert_many(data["users"])
    db.trails.insert_many(data["trails"])
    ensure_indexes(db)
    return data


def main():
    uri = os.environ.get("MONGO_URI", "mongodb://127.0.0.1:27017")
    name = os.environ.get("MONGO_DB", "trailblazer")
    db = MongoClient(uri, serverSelectionTimeoutMS=5000, tz_aware=True)[name]
    try:
        data = seed(db)
    except Exception as exc:  # noqa: BLE001 - give a friendly message for the common "Mongo not running" case
        print(f"Seeding failed: {exc}", file=sys.stderr)
        sys.exit(1)
    reviews = sum(len(t["reviews"]) for t in data["trails"])
    pois = sum(len(t["points_of_interest"]) for t in data["trails"])
    print(f"Seeded '{name}': {len(data['trails'])} trails, {reviews} reviews, {pois} points of interest, "
          f"{len(data['users'])} users")
    print(f"Admin login: admin / {ADMIN_PASSWORD}")
    print(f"Hiker login: {data['users'][1]['username']} / {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
