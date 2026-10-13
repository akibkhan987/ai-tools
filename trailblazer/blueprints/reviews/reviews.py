"""Reviews: a sub-document collection embedded in each trail document."""
from datetime import datetime, timezone

from bson import ObjectId
from flask import Blueprint, g, url_for

from ... import db
from ...decorators import is_admin, jwt_required
from ...utils import (ApiError, choice_arg, int_arg, paginated, pagination_args,
                     parse_object_id, respond)
from ...validation import REVIEW_SCHEMA, validate_request
from ..trails.trails import get_trail_or_404

reviews_bp = Blueprint("reviews", __name__)

REVIEW_SORTS = {
    "newest": [("created_at", -1)],
    "oldest": [("created_at", 1)],
    "highest": [("rating", -1), ("created_at", -1)],
    "lowest": [("rating", 1), ("created_at", -1)],
    "helpful": [("helpful_count", -1), ("created_at", -1)],
}


def refresh_rating(trail_id):
    """Recalculate the denormalised avg_rating / review_count fields with an aggregation."""
    stats = list(db.trails().aggregate([
        {"$match": {"_id": trail_id}},
        {"$project": {
            "review_count": {"$size": "$reviews"},
            "avg_rating": {"$avg": "$reviews.rating"},
        }},
    ]))
    if not stats:
        return
    avg = stats[0].get("avg_rating")
    db.trails().update_one({"_id": trail_id}, {"$set": {
        "avg_rating": round(avg, 2) if avg is not None else 0.0,
        "review_count": stats[0]["review_count"],
    }})


def get_review_or_404(trail_id, review_id):
    tid = parse_object_id(trail_id, "trail ID")
    rid = parse_object_id(review_id, "review ID")
    # $elemMatch projection returns only the matching review from the embedded array
    doc = db.trails().find_one({"_id": tid}, {"reviews": {"$elemMatch": {"_id": rid}}})
    if doc is None:
        raise ApiError(404, "Trail not found")
    if not doc.get("reviews"):
        raise ApiError(404, "Review not found")
    return tid, doc["reviews"][0]


def with_helpful_count(review):
    review["helpful_count"] = len(review.get("helpful_votes", []))
    return review


@reviews_bp.route("/trails/<trail_id>/reviews", methods=["GET"])
def list_reviews(trail_id):
    trail = get_trail_or_404(trail_id, {"_id": 1})
    page, size = pagination_args()
    sort = REVIEW_SORTS[choice_arg("sort", list(REVIEW_SORTS), "newest")]
    min_rating = int_arg("min_rating", minimum=1, maximum=5)

    pipeline = [
        {"$match": {"_id": trail["_id"]}},
        {"$unwind": "$reviews"},
        {"$replaceRoot": {"newRoot": "$reviews"}},
    ]
    if min_rating:
        pipeline.append({"$match": {"rating": {"$gte": min_rating}}})
    pipeline += [
        {"$addFields": {"helpful_count": {"$size": "$helpful_votes"}}},
        {"$sort": dict(sort)},
        # $facet runs the count and the page query over the same input in one round trip
        {"$facet": {
            "total": [{"$count": "n"}],
            "data": [{"$skip": (page - 1) * size}, {"$limit": size}],
        }},
    ]
    result = list(db.trails().aggregate(pipeline))
    facet = result[0] if result else {"total": [], "data": []}
    total = facet["total"][0]["n"] if facet["total"] else 0
    return respond(paginated(facet["data"], total, page, size))


@reviews_bp.route("/trails/<trail_id>/reviews/<review_id>", methods=["GET"])
def get_review(trail_id, review_id):
    _, review = get_review_or_404(trail_id, review_id)
    return respond(with_helpful_count(review))


@reviews_bp.route("/trails/<trail_id>/reviews", methods=["POST"])
@jwt_required
def add_review(trail_id):
    tid = parse_object_id(trail_id, "trail ID")
    data = validate_request(REVIEW_SCHEMA)
    now = datetime.now(timezone.utc)
    review = {
        "_id": ObjectId(),
        "user_id": g.user["_id"],
        "username": g.user["username"],
        **data,
        "helpful_votes": [],
        "created_at": now,
        "updated_at": now,
    }
    # The $ne condition makes "one review per user per trail" atomic: if this user
    # already has a review the filter doesn't match and nothing is pushed.
    result = db.trails().update_one(
        {"_id": tid, "reviews.user_id": {"$ne": g.user["_id"]}},
        {"$push": {"reviews": review}},
    )
    if result.matched_count == 0:
        get_trail_or_404(trail_id, {"_id": 1})  # raises 404 if the trail doesn't exist
        raise ApiError(409, "You have already reviewed this trail; edit your existing review instead")

    refresh_rating(tid)
    response = respond(with_helpful_count(review), 201)
    response.headers["Location"] = url_for("reviews.get_review", trail_id=trail_id, review_id=str(review["_id"]))
    return response


def _update_review(trail_id, review_id, partial):
    tid, review = get_review_or_404(trail_id, review_id)
    if review["user_id"] != g.user["_id"]:
        raise ApiError(403, "You can only edit your own reviews")
    data = validate_request(REVIEW_SCHEMA, partial=partial)
    data["updated_at"] = datetime.now(timezone.utc)

    # The positional operator `$` updates the array element matched in the filter
    db.trails().update_one(
        {"_id": tid, "reviews._id": review["_id"]},
        {"$set": {f"reviews.$.{key}": value for key, value in data.items()}},
    )
    refresh_rating(tid)
    _, updated = get_review_or_404(trail_id, review_id)
    return respond(with_helpful_count(updated))


@reviews_bp.route("/trails/<trail_id>/reviews/<review_id>", methods=["PUT"])
@jwt_required
def replace_review(trail_id, review_id):
    return _update_review(trail_id, review_id, partial=False)


@reviews_bp.route("/trails/<trail_id>/reviews/<review_id>", methods=["PATCH"])
@jwt_required
def patch_review(trail_id, review_id):
    return _update_review(trail_id, review_id, partial=True)


@reviews_bp.route("/trails/<trail_id>/reviews/<review_id>", methods=["DELETE"])
@jwt_required
def delete_review(trail_id, review_id):
    tid, review = get_review_or_404(trail_id, review_id)
    if review["user_id"] != g.user["_id"] and not is_admin():
        raise ApiError(403, "You can only delete your own reviews")
    db.trails().update_one({"_id": tid}, {"$pull": {"reviews": {"_id": review["_id"]}}})
    refresh_rating(tid)
    return respond({}, 204)


@reviews_bp.route("/trails/<trail_id>/reviews/<review_id>/helpful", methods=["POST"])
@jwt_required
def vote_helpful(trail_id, review_id):
    tid, review = get_review_or_404(trail_id, review_id)
    if review["user_id"] == g.user["_id"]:
        raise ApiError(403, "You cannot vote on your own review")
    if g.user["_id"] in review.get("helpful_votes", []):
        raise ApiError(409, "You have already marked this review as helpful")
    # $addToSet guarantees a user is only counted once even under concurrent requests
    db.trails().update_one({"_id": tid, "reviews._id": review["_id"]},
                           {"$addToSet": {"reviews.$.helpful_votes": g.user["_id"]}})
    _, updated = get_review_or_404(trail_id, review_id)
    return respond({"message": "Marked as helpful",
                    "helpful_count": len(updated["helpful_votes"])}, 201)


@reviews_bp.route("/trails/<trail_id>/reviews/<review_id>/helpful", methods=["DELETE"])
@jwt_required
def remove_helpful(trail_id, review_id):
    tid, review = get_review_or_404(trail_id, review_id)
    if g.user["_id"] not in review.get("helpful_votes", []):
        raise ApiError(404, "You have not marked this review as helpful")
    db.trails().update_one({"_id": tid, "reviews._id": review["_id"]},
                           {"$pull": {"reviews.$.helpful_votes": g.user["_id"]}})
    return respond({}, 204)
