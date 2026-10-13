"""Build the TrailBlazer dataset from the curated trail list.

Trails come from `trails_source.py`. User accounts, reviews, helpful votes,
favourites and completed-hike logs are generated deterministically (fixed random
seed) so every run produces the same, realistic-looking data.
"""
import random
from datetime import datetime, timedelta, timezone

import bcrypt
from bson import ObjectId

from .trails_source import TRAILS

FEATURE_KEYS = ["dog_friendly", "wheelchair_accessible", "parking", "public_transport", "toilets", "cafe"]
DEMO_PASSWORD = "Password123"
ADMIN_PASSWORD = "AdminPass123"

FIRST_NAMES = ["Aoife", "Ciaran", "Niamh", "Liam", "Siobhan", "Conor", "Emma", "Oisin", "Grace", "Rory",
               "Hannah", "Callum", "Erin", "Darragh", "Sophie", "Eoin", "Megan", "Ryan", "Chloe", "Jack",
               "Orla", "Patrick", "Isla", "Finn"]
SURNAMES = ["Murphy", "Kelly", "O'Neill", "Campbell", "Wilson", "McLaughlin", "Doherty", "Quinn", "Brown",
            "Robinson", "Thompson", "Walsh", "Stewart", "Hughes", "Smyth", "Byrne"]

REVIEW_TEXT = {
    5: [("Absolutely stunning", "One of the best walks I've done. Well-marked path and the views were worth every step."),
        ("A must-do", "Unforgettable day out. Took plenty of photos and will definitely be back with friends."),
        ("Perfect day", "Great variety of scenery and the route was easy to follow. Highly recommended.")],
    4: [("Really enjoyable", "Lovely route with great views. Some sections were busy but still well worth it."),
        ("Great walk", "Good path most of the way, a bit eroded in places. Bring proper boots."),
        ("Recommended", "Enjoyed this a lot. Parking filled up early so get there before nine.")],
    3: [("Good but busy", "Nice enough walk but very crowded at the weekend. Go midweek if you can."),
        ("Decent route", "Some lovely sections but the path was boggy and signage could be better."),
        ("Okay day out", "Weather closed in so we missed the views. Path was fine but nothing special in the mist.")],
    2: [("Disappointing", "Path was badly eroded and very muddy. Not as scenic as the photos suggest."),
        ("Harder than expected", "Took much longer than the guide time. Navigation was tricky near the top.")],
    1: [("Not for us", "Poor signage, we got lost twice and the car park was full. Wouldn't repeat it.")],
}
SEASON_MONTHS = {"winter": [12, 1, 2], "spring": [3, 4, 5], "summer": [6, 7, 8], "autumn": [9, 10, 11]}
SEASON_CONDITIONS = {"winter": ["ice", "snow", "wet", "windy"], "spring": ["wet", "muddy", "dry", "windy"],
                     "summer": ["dry", "dry", "windy", "wet"], "autumn": ["wet", "muddy", "windy", "dry"]}


def _hash(password):
    # Low cost factor keeps seeding fast; the API itself uses bcrypt's default cost
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=6)).decode()


def build_users(rng, now):
    admin = {"_id": ObjectId(), "username": "admin", "email": "admin@trailblazer.dev", "name": "Site Admin",
             "password": _hash(ADMIN_PASSWORD), "admin": True, "favourites": [], "completed": [],
             "created_at": now - timedelta(days=400)}
    users = [admin]
    demo_hash = _hash(DEMO_PASSWORD)
    used = set()
    while len(users) < 25:
        first, last = rng.choice(FIRST_NAMES), rng.choice(SURNAMES)
        username = f"{first}_{last}".lower().replace("'", "")
        if username in used:
            continue
        used.add(username)
        users.append({"_id": ObjectId(), "username": username, "email": f"{username}@example.com",
                      "name": f"{first} {last}", "password": demo_hash, "admin": False,
                      "favourites": [], "completed": [],
                      "created_at": now - timedelta(days=rng.randint(30, 380))})
    return users


def pick_rating(rng, difficulty):
    # Harder routes skew slightly lower (weather, effort) but most reviews are positive
    weights = {"easy": [1, 2, 8, 30, 45], "moderate": [1, 3, 9, 32, 42],
               "hard": [2, 4, 12, 32, 38], "strenuous": [3, 5, 12, 30, 36]}[difficulty]
    return rng.choices([1, 2, 3, 4, 5], weights=weights)[0]


def build_reviews(rng, trail, users, now):
    reviewers = rng.sample(users[1:], rng.randint(2, 12))
    reviews = []
    for user in reviewers:
        season = rng.choice(trail["best_seasons"] or ["summer"])
        month = rng.choice(SEASON_MONTHS[season])
        year = rng.choice([2024, 2025, 2026])
        hiked_on = datetime(year, month, rng.randint(1, 28), tzinfo=timezone.utc)
        if hiked_on > now:
            hiked_on = hiked_on.replace(year=year - 1)
        rating = pick_rating(rng, trail["difficulty"])
        title, comment = rng.choice(REVIEW_TEXT[rating])
        created = min(hiked_on + timedelta(days=rng.randint(0, 10), hours=rng.randint(8, 21)), now)
        voters = [u["_id"] for u in rng.sample(users[1:], rng.randint(0, 6)) if u["_id"] != user["_id"]]
        reviews.append({"_id": ObjectId(), "user_id": user["_id"], "username": user["username"],
                        "rating": rating, "title": title, "comment": comment, "hiked_on": hiked_on,
                        "conditions": rng.choice(SEASON_CONDITIONS[season]),
                        "helpful_votes": voters, "created_at": created, "updated_at": created})
    reviews.sort(key=lambda r: r["created_at"])
    return reviews


def build_trails(rng, users, now):
    admin_id = users[0]["_id"]
    trails = []
    for (name, region, country, (lat, lng), dist, ascent, mins, difficulty, route_type, tags, seasons,
         features, description, pois) in TRAILS:
        trail = {
            "_id": ObjectId(), "name": name, "description": description, "region": region, "country": country,
            "location": {"type": "Point", "coordinates": [lng, lat]},
            "distance_km": dist, "elevation_gain_m": ascent, "estimated_duration_mins": mins,
            "difficulty": difficulty, "route_type": route_type, "tags": tags, "best_seasons": seasons,
            "features": {k: features.get(k, False) for k in FEATURE_KEYS},
            "points_of_interest": [
                {"_id": ObjectId(), "name": p_name, "type": p_type,
                 "location": {"type": "Point", "coordinates": [p_lng, p_lat]}, "km_from_start": km,
                 "created_at": now - timedelta(days=300)}
                for p_name, p_type, p_lat, p_lng, km in pois
            ],
            "created_by": admin_id,
            "created_at": now - timedelta(days=rng.randint(200, 365)),
        }
        trail["updated_at"] = trail["created_at"]
        trail["reviews"] = build_reviews(rng, trail, users, now)
        ratings = [r["rating"] for r in trail["reviews"]]
        trail["review_count"] = len(ratings)
        trail["avg_rating"] = round(sum(ratings) / len(ratings), 2) if ratings else 0.0
        trails.append(trail)
    return trails


def add_user_activity(rng, users, trails):
    for user in users[1:]:
        user["favourites"] = [t["_id"] for t in rng.sample(trails, rng.randint(0, 6))]
        # Hikers' completed logs mirror the trails they reviewed, plus a few extra
        for trail in trails:
            for review in trail["reviews"]:
                if review["user_id"] == user["_id"]:
                    user["completed"].append({
                        "_id": ObjectId(), "trail_id": trail["_id"], "completed_on": review["hiked_on"],
                        "duration_mins": int(trail["estimated_duration_mins"] * rng.uniform(0.8, 1.3)),
                        "logged_at": review["created_at"]})


def build(seed=661):
    rng = random.Random(seed)
    now = datetime.now(timezone.utc)
    users = build_users(rng, now)
    trails = build_trails(rng, users, now)
    add_user_activity(rng, users, trails)
    return {"users": users, "trails": trails}
