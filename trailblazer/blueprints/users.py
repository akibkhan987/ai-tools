"""User accounts: profile, favourites, completed-hike log, personal stats and admin management."""
import re
from datetime import datetime, timezone

from bson import ObjectId
from flask import Blueprint, g, request
from pymongo.errors import DuplicateKeyError

from .. import db
from ..auth_utils import admin_required, check_password, hash_password, is_admin, jwt_required
from ..utils import (ApiError, get_json_body, paginated, pagination_args, parse_object_id, respond)
from ..validation import COMPLETION_SCHEMA, PROFILE_SCHEMA, check_password_strength, validate
from .reviews import refresh_rating
from .trails import get_trail_or_404

users_bp = Blueprint("users", __name__)

PUBLIC_FIELDS = {"password": 0}
TRAIL_CARD = {"_id": 1, "name": 1, "region": 1, "difficulty": 1, "distance_km": 1,
              "elevation_gain_m": 1, "avg_rating": 1}


# ---------- admin management ----------

@users_bp.route("/users", methods=["GET"])
@jwt_required
@admin_required
def list_users():
    page, size = pagination_args()
    query = {}
    text = request.args.get("q", "").strip()
    if text:
        pattern = {"$regex": re.escape(text), "$options": "i"}
        query["$or"] = [{"username": pattern}, {"email": pattern}, {"name": pattern}]
    total = db.users().count_documents(query)
    users = list(db.users().find(query, PUBLIC_FIELDS).sort("username", 1)
                 .skip((page - 1) * size).limit(size))
    return respond(paginated(users, total, page, size))


@users_bp.route("/users/<user_id>", methods=["GET"])
@jwt_required
def get_user(user_id):
    uid = parse_object_id(user_id, "user id")
    if uid != g.user["_id"] and not is_admin():
        raise ApiError(403, "You can only view your own account")
    user = db.users().find_one({"_id": uid}, PUBLIC_FIELDS)
    if user is None:
        raise ApiError(404, "User not found")
    return respond(user)


@users_bp.route("/users/<user_id>/role", methods=["PATCH"])
@jwt_required
@admin_required
def set_role(user_id):
    uid = parse_object_id(user_id, "user id")
    body = get_json_body()
    if not isinstance(body.get("admin"), bool):
        raise ApiError(400, "Validation failed", {"admin": "must be true or false"})
    if uid == g.user["_id"] and body["admin"] is False:
        raise ApiError(400, "You cannot remove your own admin rights")
    result = db.users().update_one({"_id": uid}, {"$set": {"admin": body["admin"]}})
    if result.matched_count == 0:
        raise ApiError(404, "User not found")
    return respond(db.users().find_one({"_id": uid}, PUBLIC_FIELDS))


@users_bp.route("/users/<user_id>", methods=["DELETE"])
@jwt_required
def delete_user(user_id):
    uid = parse_object_id(user_id, "user id")
    if uid != g.user["_id"] and not is_admin():
        raise ApiError(403, "You can only delete your own account")
    if db.users().find_one({"_id": uid}, {"_id": 1}) is None:
        raise ApiError(404, "User not found")

    # Remove the user's reviews and helpful votes everywhere, then fix the affected ratings
    reviewed = [t["_id"] for t in db.trails().find({"reviews.user_id": uid}, {"_id": 1})]
    db.trails().update_many({"reviews.user_id": uid}, {"$pull": {"reviews": {"user_id": uid}}})
    db.trails().update_many({"reviews.helpful_votes": uid},
                            {"$pull": {"reviews.$[].helpful_votes": uid}})
    for trail_id in reviewed:
        refresh_rating(trail_id)
    db.users().delete_one({"_id": uid})
    return respond({}, 204)


# ---------- own profile ----------

@users_bp.route("/users/me", methods=["GET"])
@jwt_required
def get_profile():
    return respond(g.user)


@users_bp.route("/users/me", methods=["PATCH"])
@jwt_required
def update_profile():
    body = get_json_body()
    current_password = body.pop("current_password", None)
    data = validate(body, PROFILE_SCHEMA, partial=True)

    if "password" in data or "email" in data:
        # Sensitive changes need the current password re-entered
        stored = db.users().find_one({"_id": g.user["_id"]}, {"password": 1})
        if not isinstance(current_password, str) or not check_password(current_password, stored["password"]):
            raise ApiError(403, "current_password is required and must be correct to change email or password")
    if "password" in data:
        check_password_strength(data["password"])
        data["password"] = hash_password(data["password"])
    if "email" in data:
        data["email"] = data["email"].lower()

    try:
        db.users().update_one({"_id": g.user["_id"]}, {"$set": data})
    except DuplicateKeyError:
        raise ApiError(409, "That email address is already registered")
    return respond(db.users().find_one({"_id": g.user["_id"]}, PUBLIC_FIELDS))


# ---------- favourites ----------

@users_bp.route("/users/me/favourites", methods=["GET"])
@jwt_required
def list_favourites():
    # $lookup joins the stored trail ids to the trails collection
    result = list(db.users().aggregate([
        {"$match": {"_id": g.user["_id"]}},
        {"$lookup": {"from": "trails", "localField": "favourites", "foreignField": "_id", "as": "trails"}},
        {"$project": {"trails": 1}},
    ]))
    trails = result[0]["trails"] if result else []
    cards = [{k: t[k] for k in TRAIL_CARD if k in t} for t in trails]
    return respond({"data": cards, "count": len(cards)})


@users_bp.route("/users/me/favourites/<trail_id>", methods=["PUT"])
@jwt_required
def add_favourite(trail_id):
    trail = get_trail_or_404(trail_id, {"_id": 1})
    result = db.users().update_one({"_id": g.user["_id"]}, {"$addToSet": {"favourites": trail["_id"]}})
    created = result.modified_count == 1
    return respond({"message": "Added to favourites" if created else "Already in favourites",
                    "trail_id": trail["_id"]}, 201 if created else 200)


@users_bp.route("/users/me/favourites/<trail_id>", methods=["DELETE"])
@jwt_required
def remove_favourite(trail_id):
    tid = parse_object_id(trail_id, "trail id")
    result = db.users().update_one({"_id": g.user["_id"], "favourites": tid}, {"$pull": {"favourites": tid}})
    if result.matched_count == 0:
        raise ApiError(404, "Trail is not in your favourites")
    return respond({}, 204)


# ---------- completed hikes log ----------

@users_bp.route("/users/me/completed", methods=["GET"])
@jwt_required
def list_completed():
    entries = list(db.users().aggregate([
        {"$match": {"_id": g.user["_id"]}},
        {"$unwind": "$completed"},
        {"$replaceRoot": {"newRoot": "$completed"}},
        {"$lookup": {"from": "trails", "localField": "trail_id", "foreignField": "_id", "as": "trail"}},
        {"$unwind": "$trail"},
        {"$project": {"_id": 1, "completed_on": 1, "duration_mins": 1,
                      "trail._id": 1, "trail.name": 1, "trail.region": 1, "trail.distance_km": 1,
                      "trail.difficulty": 1}},
        {"$sort": {"completed_on": -1}},
    ]))
    return respond({"data": entries, "count": len(entries)})


@users_bp.route("/users/me/completed", methods=["POST"])
@jwt_required
def log_completion():
    data = validate(get_json_body(), COMPLETION_SCHEMA)
    trail = get_trail_or_404(data["trail_id"], {"_id": 1})
    entry = {"_id": ObjectId(), "trail_id": trail["_id"], "completed_on": data["completed_on"],
             "logged_at": datetime.now(timezone.utc)}
    if "duration_mins" in data:
        entry["duration_mins"] = data["duration_mins"]
    db.users().update_one({"_id": g.user["_id"]}, {"$push": {"completed": entry}})
    return respond(entry, 201)


@users_bp.route("/users/me/completed/<entry_id>", methods=["DELETE"])
@jwt_required
def delete_completion(entry_id):
    eid = parse_object_id(entry_id, "entry id")
    result = db.users().update_one({"_id": g.user["_id"], "completed._id": eid},
                                   {"$pull": {"completed": {"_id": eid}}})
    if result.matched_count == 0:
        raise ApiError(404, "Completed-hike entry not found")
    return respond({}, 204)


@users_bp.route("/users/me/stats", methods=["GET"])
@jwt_required
def my_stats():
    """Personal totals computed with $unwind + $lookup + $group."""
    result = list(db.users().aggregate([
        {"$match": {"_id": g.user["_id"]}},
        {"$unwind": "$completed"},
        {"$lookup": {"from": "trails", "localField": "completed.trail_id", "foreignField": "_id", "as": "trail"}},
        {"$unwind": "$trail"},
        {"$group": {
            "_id": None,
            "hikes_completed": {"$sum": 1},
            "unique_trails": {"$addToSet": "$trail._id"},
            "regions": {"$addToSet": "$trail.region"},
            "total_distance_km": {"$sum": "$trail.distance_km"},
            "total_elevation_m": {"$sum": "$trail.elevation_gain_m"},
            "longest_hike_km": {"$max": "$trail.distance_km"},
        }},
    ]))
    reviews_written = db.trails().count_documents({"reviews.user_id": g.user["_id"]})
    if not result:
        return respond({"hikes_completed": 0, "unique_trails": 0, "regions_visited": [],
                        "total_distance_km": 0, "total_elevation_m": 0, "longest_hike_km": 0,
                        "reviews_written": reviews_written})
    s = result[0]
    return respond({
        "hikes_completed": s["hikes_completed"],
        "unique_trails": len(s["unique_trails"]),
        "regions_visited": sorted(s["regions"]),
        "total_distance_km": round(s["total_distance_km"], 2),
        "total_elevation_m": s["total_elevation_m"],
        "longest_hike_km": s["longest_hike_km"],
        "reviews_written": reviews_written,
    })
