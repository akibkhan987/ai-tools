"""Read-only analytics endpoints built on MongoDB aggregation pipelines."""
import re

from flask import Blueprint, request

from .. import db
from ..utils import int_arg, respond

stats_bp = Blueprint("stats", __name__)


def round_field(expr, places=2):
    return {"$round": [expr, places]}


@stats_bp.route("/stats/overview", methods=["GET"])
def overview():
    result = list(db.trails().aggregate([
        {"$group": {
            "_id": None,
            "trails": {"$sum": 1},
            "reviews": {"$sum": "$review_count"},
            "total_distance_km": {"$sum": "$distance_km"},
            "avg_distance_km": {"$avg": "$distance_km"},
            "highest_elevation_gain_m": {"$max": "$elevation_gain_m"},
            "regions": {"$addToSet": "$region"},
        }},
    ]))
    if not result:
        return respond({"trails": 0, "reviews": 0, "users": db.users().count_documents({})})
    s = result[0]
    return respond({
        "trails": s["trails"],
        "reviews": s["reviews"],
        "users": db.users().count_documents({}),
        "regions": len(s["regions"]),
        "total_distance_km": round(s["total_distance_km"], 1),
        "avg_distance_km": round(s["avg_distance_km"], 2),
        "highest_elevation_gain_m": s["highest_elevation_gain_m"],
    })


@stats_bp.route("/stats/regions", methods=["GET"])
def by_region():
    data = list(db.trails().aggregate([
        {"$group": {
            "_id": "$region",
            "country": {"$first": "$country"},
            "trail_count": {"$sum": 1},
            "avg_distance_km": {"$avg": "$distance_km"},
            "avg_elevation_gain_m": {"$avg": "$elevation_gain_m"},
            "total_reviews": {"$sum": "$review_count"},
            # Only rated trails count towards the regional average
            "avg_rating": {"$avg": {"$cond": [{"$gt": ["$review_count", 0]}, "$avg_rating", None]}},
        }},
        {"$project": {
            "_id": 0, "region": "$_id", "country": 1, "trail_count": 1, "total_reviews": 1,
            "avg_distance_km": round_field("$avg_distance_km"),
            "avg_elevation_gain_m": round_field("$avg_elevation_gain_m", 0),
            "avg_rating": round_field("$avg_rating"),
        }},
        {"$sort": {"trail_count": -1, "region": 1}},
    ]))
    return respond({"data": data, "count": len(data)})


@stats_bp.route("/stats/difficulty", methods=["GET"])
def by_difficulty():
    order = {"easy": 0, "moderate": 1, "hard": 2, "strenuous": 3}
    data = list(db.trails().aggregate([
        {"$group": {
            "_id": "$difficulty",
            "trail_count": {"$sum": 1},
            "avg_distance_km": {"$avg": "$distance_km"},
            "avg_elevation_gain_m": {"$avg": "$elevation_gain_m"},
            "avg_duration_mins": {"$avg": "$estimated_duration_mins"},
        }},
        {"$project": {
            "_id": 0, "difficulty": "$_id", "trail_count": 1,
            "avg_distance_km": round_field("$avg_distance_km"),
            "avg_elevation_gain_m": round_field("$avg_elevation_gain_m", 0),
            "avg_duration_mins": round_field("$avg_duration_mins", 0),
        }},
    ]))
    data.sort(key=lambda d: order.get(d["difficulty"], 99))
    return respond({"data": data})


@stats_bp.route("/stats/distance-bands", methods=["GET"])
def distance_bands():
    """$bucket groups trails into distance ranges, like a histogram."""
    data = list(db.trails().aggregate([
        {"$bucket": {
            "groupBy": "$distance_km",
            "boundaries": [0, 5, 10, 15, 20, 30],
            "default": "30+",
            "output": {"trail_count": {"$sum": 1}, "trails": {"$push": "$name"}},
        }},
    ]))
    labels = {0: "0-5 km", 5: "5-10 km", 10: "10-15 km", 15: "15-20 km", 20: "20-30 km", "30+": "30+ km"}
    return respond({"data": [
        {"band": labels.get(b["_id"], str(b["_id"])), "trail_count": b["trail_count"], "trails": b["trails"]}
        for b in data
    ]})


@stats_bp.route("/stats/tags", methods=["GET"])
def popular_tags():
    limit = int_arg("limit", 15, minimum=1, maximum=100)
    data = list(db.trails().aggregate([
        {"$unwind": "$tags"},
        {"$group": {"_id": "$tags", "trail_count": {"$sum": 1}, "avg_rating": {"$avg": "$avg_rating"}}},
        {"$sort": {"trail_count": -1, "_id": 1}},
        {"$limit": limit},
        {"$project": {"_id": 0, "tag": "$_id", "trail_count": 1, "avg_rating": round_field("$avg_rating")}},
    ]))
    return respond({"data": data})


@stats_bp.route("/stats/top-rated", methods=["GET"])
def top_rated():
    limit = int_arg("limit", 10, minimum=1, maximum=50)
    min_reviews = int_arg("min_reviews", 3, minimum=1)
    match = {"review_count": {"$gte": min_reviews}}
    region = request.args.get("region", "").strip()
    if region:
        match["region"] = {"$regex": f"^{re.escape(region)}$", "$options": "i"}
    data = list(db.trails().aggregate([
        {"$match": match},
        {"$sort": {"avg_rating": -1, "review_count": -1, "name": 1}},
        {"$limit": limit},
        {"$project": {"name": 1, "region": 1, "difficulty": 1, "distance_km": 1,
                      "avg_rating": 1, "review_count": 1}},
    ]))
    return respond({"data": data, "min_reviews": min_reviews})


@stats_bp.route("/stats/reviews/monthly", methods=["GET"])
def reviews_by_month():
    """Review volume and average rating per calendar month of the hike."""
    data = list(db.trails().aggregate([
        {"$unwind": "$reviews"},
        {"$group": {
            "_id": {"year": {"$year": "$reviews.hiked_on"}, "month": {"$month": "$reviews.hiked_on"}},
            "review_count": {"$sum": 1},
            "avg_rating": {"$avg": "$reviews.rating"},
        }},
        {"$sort": {"_id.year": 1, "_id.month": 1}},
        {"$project": {"_id": 0, "year": "$_id.year", "month": "$_id.month", "review_count": 1,
                      "avg_rating": round_field("$avg_rating")}},
    ]))
    return respond({"data": data})


@stats_bp.route("/stats/conditions", methods=["GET"])
def conditions_report():
    """How reported trail conditions relate to ratings."""
    data = list(db.trails().aggregate([
        {"$unwind": "$reviews"},
        {"$match": {"reviews.conditions": {"$exists": True}}},
        {"$group": {"_id": "$reviews.conditions", "reports": {"$sum": 1},
                    "avg_rating": {"$avg": "$reviews.rating"}}},
        {"$sort": {"reports": -1}},
        {"$project": {"_id": 0, "conditions": "$_id", "reports": 1, "avg_rating": round_field("$avg_rating")}},
    ]))
    return respond({"data": data})
