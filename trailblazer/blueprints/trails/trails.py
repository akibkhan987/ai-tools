"""Trail resources: CRUD, multi-field filtering, sorting, pagination and geo search."""
import re
from datetime import datetime, timezone

from flask import Blueprint, g, request, url_for

from ... import db
from ...decorators import is_admin, jwt_required
from ...utils import (ApiError, bool_arg, choice_arg, float_arg, int_arg,
                     paginated, pagination_args, parse_object_id, respond)
from ...validation import DIFFICULTIES, FEATURE_KEYS, ROUTE_TYPES, SEASONS, TRAIL_SCHEMA, validate_request

trails_bp = Blueprint("trails", __name__)

SORTABLE_FIELDS = ["name", "distance_km", "elevation_gain_m", "estimated_duration_mins",
                   "avg_rating", "review_count", "created_at"]
# Embedded arrays are left out of list views to keep responses small
SUMMARY_PROJECTION = {"reviews": 0, "points_of_interest": 0}


def get_trail_or_404(trail_id, projection=None):
    trail = db.trails().find_one({"_id": parse_object_id(trail_id, "trail ID")}, projection)
    if trail is None:
        raise ApiError(404, "Trail not found")
    return trail


def ensure_can_modify(trail):
    """Only the user who created a trail, or an admin, may change it."""
    if not is_admin() and trail.get("created_by") != g.user["_id"]:
        raise ApiError(403, "Only the trail's creator or an admin can modify this trail")


def csv_arg(name, allowed=None):
    raw = request.args.get(name)
    if not raw:
        return []
    values = [v.strip().lower() for v in raw.split(",") if v.strip()]
    if allowed:
        invalid = [v for v in values if v not in allowed]
        if invalid:
            raise ApiError(400, f"Invalid value(s) for '{name}': {', '.join(invalid)}",
                           {"allowed": allowed})
    return values


def build_trail_filter():
    """Translate query-string parameters into a MongoDB filter document."""
    query = {}

    text = request.args.get("q", "").strip()
    if text:
        # re.escape stops user input being interpreted as a regular expression
        pattern = {"$regex": re.escape(text), "$options": "i"}
        query["$or"] = [{"name": pattern}, {"description": pattern}, {"region": pattern}]

    for field in ("region", "country"):
        value = request.args.get(field, "").strip()
        if value:
            query[field] = {"$regex": f"^{re.escape(value)}$", "$options": "i"}

    difficulties = csv_arg("difficulty", DIFFICULTIES)
    if difficulties:
        query["difficulty"] = {"$in": difficulties}

    route_types = csv_arg("route_type", ROUTE_TYPES)
    if route_types:
        query["route_type"] = {"$in": route_types}

    ranges = {
        "distance_km": ("min_distance", "max_distance"),
        "elevation_gain_m": ("min_elevation", "max_elevation"),
        "estimated_duration_mins": ("min_duration", "max_duration"),
    }
    for field, (low_name, high_name) in ranges.items():
        low, high = float_arg(low_name, minimum=0), float_arg(high_name, minimum=0)
        if low is not None and high is not None and low > high:
            raise ApiError(400, f"'{low_name}' cannot be greater than '{high_name}'")
        bounds = {}
        if low is not None:
            bounds["$gte"] = low
        if high is not None:
            bounds["$lte"] = high
        if bounds:
            query[field] = bounds

    min_rating = float_arg("min_rating", minimum=0, maximum=5)
    if min_rating is not None:
        query["avg_rating"] = {"$gte": min_rating}

    tags = csv_arg("tags")
    if tags:
        match_mode = choice_arg("tag_match", ["all", "any"], "any")
        query["tags"] = {"$all": tags} if match_mode == "all" else {"$in": tags}

    seasons = csv_arg("season", SEASONS)
    if seasons:
        query["best_seasons"] = {"$all": seasons}

    for feature in FEATURE_KEYS:
        flag = bool_arg(feature)
        if flag is not None:
            query[f"features.{feature}"] = flag

    return query


@trails_bp.route("/trails", methods=["GET"])
def list_trails():
    page, size = pagination_args()
    query = build_trail_filter()
    sort_field = choice_arg("sort", SORTABLE_FIELDS, "name")
    direction = 1 if choice_arg("order", ["asc", "desc"], "asc") == "asc" else -1

    total = db.trails().count_documents(query)
    cursor = (db.trails().find(query, SUMMARY_PROJECTION)
              # _id as a tie-breaker gives stable ordering across pages
              .sort([(sort_field, direction), ("_id", 1)])
              .skip((page - 1) * size)
              .limit(size))
    return respond(paginated(list(cursor), total, page, size))


@trails_bp.route("/trails/<trail_id>", methods=["GET"])
def get_trail(trail_id):
    # $slice returns only the 3 most recent reviews; the full list is paginated under /reviews
    trail = get_trail_or_404(trail_id, {"reviews": {"$slice": -3}})
    trail["latest_reviews"] = list(reversed(trail.pop("reviews", [])))
    return respond(trail)


@trails_bp.route("/trails", methods=["POST"])
@jwt_required
def create_trail():
    data = validate_request(TRAIL_SCHEMA)
    duplicate = db.trails().find_one({
        "name": {"$regex": f"^{re.escape(data['name'])}$", "$options": "i"},
        "region": data["region"],
    })
    if duplicate:
        raise ApiError(409, "A trail with this name already exists in this region")

    now = datetime.now(timezone.utc)
    trail = {
        **data,
        "tags": data.get("tags", []),
        "best_seasons": data.get("best_seasons", []),
        "features": {key: data.get("features", {}).get(key, False) for key in FEATURE_KEYS},
        "avg_rating": 0.0,
        "review_count": 0,
        "reviews": [],
        "points_of_interest": [],
        "created_by": g.user["_id"],
        "created_at": now,
        "updated_at": now,
    }
    result = db.trails().insert_one(trail)
    trail["_id"] = result.inserted_id
    response = respond(trail, 201)
    response.headers["Location"] = url_for("trails.get_trail", trail_id=str(result.inserted_id))
    return response


def _update_trail(trail_id, partial):
    trail = get_trail_or_404(trail_id, {"created_by": 1, "features": 1})
    ensure_can_modify(trail)
    data = validate_request(TRAIL_SCHEMA, partial=partial)

    if "features" in data:
        # Merge so a PATCH of one flag doesn't wipe the others
        merged = {key: trail.get("features", {}).get(key, False) for key in FEATURE_KEYS}
        merged.update(data["features"])
        data["features"] = merged
    data["updated_at"] = datetime.now(timezone.utc)

    db.trails().update_one({"_id": trail["_id"]}, {"$set": data})
    return respond(db.trails().find_one({"_id": trail["_id"]}, SUMMARY_PROJECTION))


@trails_bp.route("/trails/<trail_id>", methods=["PUT"])
@jwt_required
def replace_trail(trail_id):
    """PUT requires every required field (full replacement of editable fields)."""
    return _update_trail(trail_id, partial=False)


@trails_bp.route("/trails/<trail_id>", methods=["PATCH"])
@jwt_required
def patch_trail(trail_id):
    """PATCH updates only the fields supplied."""
    return _update_trail(trail_id, partial=True)


@trails_bp.route("/trails/<trail_id>", methods=["DELETE"])
@jwt_required
def delete_trail(trail_id):
    trail = get_trail_or_404(trail_id, {"created_by": 1})
    ensure_can_modify(trail)
    db.trails().delete_one({"_id": trail["_id"]})
    # Keep users' favourites/completions consistent with the deleted trail
    db.users().update_many({}, {"$pull": {"favourites": trail["_id"], "completed": {"trail_id": trail["_id"]}}})
    return respond({}, 204)


def geo_near_pipeline(lng, lat, radius_km, limit, extra_match=None):
    """$geoNear must be the first stage; it sorts by distance and adds `distance_km`."""
    return [
        {"$geoNear": {
            "near": {"type": "Point", "coordinates": [lng, lat]},
            "distanceField": "distance_m",
            "maxDistance": radius_km * 1000,
            "spherical": True,
            "query": extra_match or {},
        }},
        {"$limit": limit},
        {"$addFields": {"distance_km": {"$round": [{"$divide": ["$distance_m", 1000]}, 2]}}},
        {"$project": {"reviews": 0, "points_of_interest": 0, "distance_m": 0}},
    ]


@trails_bp.route("/trails/nearby", methods=["GET"])
def nearby_trails():
    lat = float_arg("lat", minimum=-90, maximum=90)
    lng = float_arg("lng", minimum=-180, maximum=180)
    if lat is None or lng is None:
        raise ApiError(400, "Query parameters 'lat' and 'lng' are required")
    radius_km = float_arg("radius_km", 25, minimum=0.1, maximum=500)
    limit = int_arg("limit", 10, minimum=1, maximum=50)

    extra = {}
    difficulties = csv_arg("difficulty", DIFFICULTIES)
    if difficulties:
        extra["difficulty"] = {"$in": difficulties}

    results = list(db.trails().aggregate(geo_near_pipeline(lng, lat, radius_km, limit, extra)))
    return respond({"data": results, "count": len(results),
                    "centre": {"latitude": lat, "longitude": lng}, "radius_km": radius_km})


@trails_bp.route("/trails/<trail_id>/nearby", methods=["GET"])
def trails_near_trail(trail_id):
    trail = get_trail_or_404(trail_id, {"location": 1, "name": 1})
    radius_km = float_arg("radius_km", 15, minimum=0.1, maximum=500)
    limit = int_arg("limit", 5, minimum=1, maximum=50)
    lng, lat = trail["location"]["coordinates"]
    pipeline = geo_near_pipeline(lng, lat, radius_km, limit, {"_id": {"$ne": trail["_id"]}})
    results = list(db.trails().aggregate(pipeline))
    return respond({"trail": {"_id": trail["_id"], "name": trail["name"]},
                    "data": results, "count": len(results), "radius_km": radius_km})
