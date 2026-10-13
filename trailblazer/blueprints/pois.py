"""Points of interest: a second embedded sub-document collection on each trail."""
from datetime import datetime, timezone

from bson import ObjectId
from flask import Blueprint, request, url_for

from .. import db
from ..auth_utils import jwt_required
from ..utils import ApiError, choice_arg, get_json_body, parse_object_id, respond
from ..validation import POI_SCHEMA, POI_TYPES, validate
from .trails import ensure_can_modify, get_trail_or_404

pois_bp = Blueprint("pois", __name__)


def get_poi_or_404(trail, poi_id):
    pid = parse_object_id(poi_id, "point of interest id")
    for poi in trail.get("points_of_interest", []):
        if poi["_id"] == pid:
            return poi
    raise ApiError(404, "Point of interest not found")


@pois_bp.route("/trails/<trail_id>/pois", methods=["GET"])
def list_pois(trail_id):
    trail = get_trail_or_404(trail_id, {"points_of_interest": 1})
    pois = trail.get("points_of_interest", [])
    poi_type = choice_arg("type", POI_TYPES)
    if poi_type:
        pois = [p for p in pois if p["type"] == poi_type]
    # Ordered along the route; POIs without a position go last
    pois.sort(key=lambda p: (p.get("km_from_start") is None, p.get("km_from_start") or 0))
    return respond({"data": pois, "count": len(pois)})


@pois_bp.route("/trails/<trail_id>/pois/<poi_id>", methods=["GET"])
def get_poi(trail_id, poi_id):
    trail = get_trail_or_404(trail_id, {"points_of_interest": 1})
    return respond(get_poi_or_404(trail, poi_id))


@pois_bp.route("/trails/<trail_id>/pois", methods=["POST"])
@jwt_required
def add_poi(trail_id):
    trail = get_trail_or_404(trail_id, {"created_by": 1, "distance_km": 1})
    ensure_can_modify(trail)
    data = validate(get_json_body(), POI_SCHEMA)
    if data.get("km_from_start", 0) > trail["distance_km"]:
        raise ApiError(400, "Validation failed",
                       {"km_from_start": f"cannot exceed the trail distance ({trail['distance_km']} km)"})
    poi = {"_id": ObjectId(), **data, "created_at": datetime.now(timezone.utc)}
    db.trails().update_one({"_id": trail["_id"]}, {"$push": {"points_of_interest": poi}})
    response = respond(poi, 201)
    response.headers["Location"] = url_for("pois.get_poi", trail_id=trail_id, poi_id=str(poi["_id"]))
    return response


@pois_bp.route("/trails/<trail_id>/pois/<poi_id>", methods=["PATCH", "PUT"])
@jwt_required
def update_poi(trail_id, poi_id):
    trail = get_trail_or_404(trail_id, {"created_by": 1, "distance_km": 1, "points_of_interest": 1})
    ensure_can_modify(trail)
    poi = get_poi_or_404(trail, poi_id)
    data = validate(get_json_body(), POI_SCHEMA, partial=request.method == "PATCH")
    if data.get("km_from_start", 0) > trail["distance_km"]:
        raise ApiError(400, "Validation failed",
                       {"km_from_start": f"cannot exceed the trail distance ({trail['distance_km']} km)"})
    db.trails().update_one(
        {"_id": trail["_id"], "points_of_interest._id": poi["_id"]},
        {"$set": {f"points_of_interest.$.{k}": v for k, v in data.items()}},
    )
    return respond({**poi, **data})


@pois_bp.route("/trails/<trail_id>/pois/<poi_id>", methods=["DELETE"])
@jwt_required
def delete_poi(trail_id, poi_id):
    trail = get_trail_or_404(trail_id, {"created_by": 1, "points_of_interest": 1})
    ensure_can_modify(trail)
    poi = get_poi_or_404(trail, poi_id)
    db.trails().update_one({"_id": trail["_id"]}, {"$pull": {"points_of_interest": {"_id": poi["_id"]}}})
    return respond({}, 204)
