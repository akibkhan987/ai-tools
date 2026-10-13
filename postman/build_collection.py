"""Generate the Postman collection (v2.1) for the TrailBlazer API.

    python postman/build_collection.py

Writes postman/TrailBlazer.postman_collection.json. Import it into Postman and use
"Run collection" to execute every request and its tests in order.
"""
import json
from pathlib import Path

OUT = Path(__file__).with_name("TrailBlazer.postman_collection.json")


def to_form(body):
    """Flatten a body into x-www-form-urlencoded fields, the format used in the module practicals.

    location -> latitude/longitude, features -> one flag per feature, lists -> comma-separated text.
    """
    fields = []
    for key, value in body.items():
        if key == "location":
            fields += [("latitude", value["latitude"]), ("longitude", value["longitude"])]
        elif key == "features":
            fields += list(value.items())
        elif isinstance(value, list):
            fields.append((key, ",".join(value)))
        else:
            fields.append((key, value))
    return [{"key": k, "value": str(v).lower() if isinstance(v, bool) else str(v), "type": "text"}
            for k, v in fields]


def req(name, method, path, tests=(), body=None, auth="hiker", query=None, prerequest=None, description="",
        as_json=False):
    """Build one Postman request item. `auth` is 'hiker', 'admin' or None.

    Bodies are sent as x-www-form-urlencoded unless as_json=True.
    """
    raw_path = path + ("?" + "&".join(f"{k}={v}" for k, v in query.items()) if query else "")
    headers = []
    if auth:
        headers.append({"key": "x-access-token", "value": "{{token}}" if auth == "hiker" else "{{admin_token}}"})
    if body is not None and as_json:
        headers.append({"key": "Content-Type", "value": "application/json"})
    item = {
        "name": name,
        "request": {
            "method": method,
            "header": headers,
            "url": {
                "raw": "{{base_url}}" + raw_path,
                "host": ["{{base_url}}"],
                "path": [p for p in path.strip("/").split("/")],
                **({"query": [{"key": k, "value": str(v)} for k, v in query.items()]} if query else {}),
            },
            "description": description,
        },
        "event": [],
    }
    if body is not None and as_json:
        item["request"]["body"] = {"mode": "raw", "raw": json.dumps(body, indent=2),
                                   "options": {"raw": {"language": "json"}}}
    elif body is not None:
        item["request"]["body"] = {"mode": "urlencoded", "urlencoded": to_form(body)}
    if tests:
        item["event"].append({"listen": "test", "script": {"type": "text/javascript", "exec": list(tests)}})
    if prerequest:
        item["event"].append({"listen": "prerequest", "script": {"type": "text/javascript", "exec": list(prerequest)}})
    return item


def status(code):
    return f'pm.test("Status code is {code}", () => pm.response.to.have.status({code}));'


def has_error():
    return 'pm.test("Error message returned", () => pm.expect(pm.response.json()).to.have.property("error"));'


def set_var(name, expr):
    return f'pm.collectionVariables.set("{name}", {expr});'


def folder(name, items, description=""):
    return {"name": name, "item": items, "description": description}


NEW_TRAIL = {
    "name": "Postman Test Loop",
    "description": "A short circular walk created by the Postman test run.",
    "region": "Belfast Hills",
    "country": "Northern Ireland",
    "location": {"latitude": 54.62, "longitude": -5.99},
    "distance_km": 5.5,
    "elevation_gain_m": 180,
    "estimated_duration_mins": 110,
    "difficulty": "easy",
    "route_type": "circular",
    "tags": ["views", "city"],
    "best_seasons": ["spring", "summer", "autumn"],
    "features": {"dog_friendly": True, "parking": True},
}

auth = folder("Auth", [
    req("Register new user", "POST", "/auth/register", auth=None,
        prerequest=[set_var("username", '"hiker_" + Date.now()')],
        body={"username": "{{username}}", "email": "{{username}}@example.com", "password": "{{password}}",
              "name": "Postman Hiker"},
        tests=[status(201),
               'const user = pm.response.json().user;',
               'pm.test("Password is not returned", () => pm.expect(user).to.not.have.property("password"));',
               'pm.test("New users are not admins", () => pm.expect(user.admin).to.be.false);',
               set_var("user_id", "user._id")]),
    req("Register duplicate username", "POST", "/auth/register", auth=None,
        body={"username": "{{username}}", "email": "other_{{username}}@example.com", "password": "{{password}}",
              "name": "Duplicate"},
        tests=[status(409), has_error()]),
    req("Register with invalid data", "POST", "/auth/register", auth=None,
        body={"username": "x!", "email": "not-an-email", "password": "short"},
        tests=[status(400),
               'const d = pm.response.json().details;',
               'pm.test("Each invalid field is reported", () => pm.expect(d).to.have.all.keys("username", "email", "password", "name"));']),
    req("Login with wrong password", "POST", "/auth/login", auth=None,
        tests=[status(401), has_error()]),
    {**req("Login as new user (Basic Auth)", "POST", "/auth/login", auth=None,
           tests=[status(200),
                  'pm.test("Token returned", () => pm.expect(pm.response.json().token).to.be.a("string"));',
                  set_var("token", "pm.response.json().token")])},
    {**req("Login as admin (Basic Auth)", "POST", "/auth/login", auth=None,
           tests=[status(200),
                  'pm.test("Admin flag set", () => pm.expect(pm.response.json().user.admin).to.be.true);',
                  set_var("admin_token", "pm.response.json().token")])},
    req("Get current user", "GET", "/auth/me",
        tests=[status(200),
               'pm.test("Correct user", () => pm.expect(pm.response.json().username).to.eql(pm.collectionVariables.get("username")));']),
    req("Get current user without token", "GET", "/auth/me", auth=None, tests=[status(401), has_error()]),
], "Registration, login (HTTP Basic Auth) and JWT handling.")

# Postman stores Basic Auth on the request's "auth" block
auth["item"][3]["request"]["auth"] = {"type": "basic", "basic": [
    {"key": "username", "value": "{{username}}"}, {"key": "password", "value": "wrong-password"}]}
auth["item"][4]["request"]["auth"] = {"type": "basic", "basic": [
    {"key": "username", "value": "{{username}}"}, {"key": "password", "value": "{{password}}"}]}
auth["item"][5]["request"]["auth"] = {"type": "basic", "basic": [
    {"key": "username", "value": "admin"}, {"key": "password", "value": "{{admin_password}}"}]}

trails = folder("Trails", [
    req("List trails (page 1, 5 per page)", "GET", "/trails", auth=None, query={"pn": 1, "ps": 5},
        tests=[status(200),
               'const body = pm.response.json();',
               'pm.test("Five trails returned", () => pm.expect(body.data.length).to.eql(5));',
               'pm.test("Pagination metadata present", () => pm.expect(body).to.include.keys("this_page", "number_of_pages", "page_size", "total"));',
               'pm.test("Embedded reviews are excluded from list view", () => pm.expect(body.data[0]).to.not.have.property("reviews"));']),
    req("Filter trails (easy/moderate, dog friendly, max 10 km)", "GET", "/trails", auth=None,
        query={"difficulty": "easy,moderate", "dog_friendly": "true", "max_distance": 10, "ps": 50},
        tests=[status(200),
               'pm.response.json().data.forEach(t => {',
               '  pm.test(t.name + " matches filters", () => {',
               '    pm.expect(["easy", "moderate"]).to.include(t.difficulty);',
               '    pm.expect(t.features.dog_friendly).to.be.true;',
               '    pm.expect(t.distance_km).to.be.at.most(10);',
               '  });',
               '});']),
    req("Filter trails with all tags", "GET", "/trails", auth=None,
        query={"tags": "coastal,cliffs", "tag_match": "all"},
        tests=[status(200),
               'pm.test("Every trail has both tags", () => pm.response.json().data.forEach(t => pm.expect(t.tags).to.include.members(["coastal", "cliffs"])));']),
    req("Search trails by keyword", "GET", "/trails", auth=None, query={"q": "mourne"},
        tests=[status(200),
               'pm.test("Results found", () => pm.expect(pm.response.json().total).to.be.above(0));']),
    req("Sort trails by rating (desc)", "GET", "/trails", auth=None, query={"sort": "avg_rating", "order": "desc"},
        tests=[status(200),
               'const r = pm.response.json().data.map(t => t.avg_rating);',
               'pm.test("Sorted by rating descending", () => pm.expect(r).to.eql([...r].sort((a, b) => b - a)));']),
    req("Invalid filter value", "GET", "/trails", auth=None, query={"difficulty": "extreme"},
        tests=[status(400), has_error()]),
    req("Trails near a point (Newcastle, Co. Down)", "GET", "/trails/nearby", auth=None,
        query={"lat": 54.2108, "lng": -5.892, "radius_km": 25},
        tests=[status(200),
               'const d = pm.response.json().data.map(t => t.distance_km);',
               'pm.test("At least one trail found", () => pm.expect(d.length).to.be.above(0));',
               'pm.test("Sorted nearest first", () => pm.expect(d).to.eql([...d].sort((a, b) => a - b)));',
               'pm.test("All within radius", () => d.forEach(x => pm.expect(x).to.be.at.most(25)));']),
    req("Nearby without coordinates", "GET", "/trails/nearby", auth=None, tests=[status(400), has_error()]),
    req("Create trail", "POST", "/trails", body=NEW_TRAIL,
        tests=[status(201),
               'const t = pm.response.json();',
               'pm.test("Location stored as GeoJSON", () => pm.expect(t.location).to.eql({type: "Point", coordinates: [-5.99, 54.62]}));',
               'pm.test("Missing features default to false", () => pm.expect(t.features.cafe).to.be.false);',
               'pm.test("Location header set", () => pm.expect(pm.response.headers.get("Location")).to.include(t._id));',
               set_var("trail_id", "t._id")]),
    req("Create trail with invalid data", "POST", "/trails",
        body={**NEW_TRAIL, "distance_km": -3, "difficulty": "extreme", "location": {"latitude": 200, "longitude": 0}},
        tests=[status(400),
               'pm.test("Field errors listed", () => pm.expect(pm.response.json().details).to.have.all.keys("distance_km", "difficulty", "location"));']),
    req("Create trail without token (JSON body)", "POST", "/trails", auth=None, body=NEW_TRAIL, as_json=True,
        tests=[status(401)]),
    req("Get one trail", "GET", "/trails/{{trail_id}}", auth=None,
        tests=[status(200),
               'pm.test("Correct trail", () => pm.expect(pm.response.json().name).to.eql("Postman Test Loop"));']),
    req("Get trail with invalid id", "GET", "/trails/12345", auth=None, tests=[status(404), has_error()]),
    req("Get trail that does not exist", "GET", "/trails/000000000000000000000000", auth=None,
        tests=[status(404), has_error()]),
    req("Update trail (PATCH, JSON body)", "PATCH", "/trails/{{trail_id}}", as_json=True,
        body={"distance_km": 6.2, "features": {"cafe": True}},
        tests=[status(200),
               'const t = pm.response.json();',
               'pm.test("Distance updated", () => pm.expect(t.distance_km).to.eql(6.2));',
               'pm.test("Other features kept", () => pm.expect(t.features.dog_friendly).to.be.true);']),
    req("Replace trail (PUT) with missing fields", "PUT", "/trails/{{trail_id}}", body={"distance_km": 4},
        tests=[status(400), has_error()]),
    req("Trails near this trail", "GET", "/trails/{{trail_id}}/nearby", auth=None, query={"radius_km": 20},
        tests=[status(200),
               'pm.test("Trail itself excluded", () => pm.response.json().data.forEach(t => pm.expect(t._id).to.not.eql(pm.collectionVariables.get("trail_id"))));']),
], "Trail CRUD plus filtering, searching, sorting, pagination and geospatial queries.")

pois = folder("Points of interest", [
    req("Add point of interest", "POST", "/trails/{{trail_id}}/pois",
        body={"name": "Summit viewpoint", "type": "viewpoint", "location": {"latitude": 54.625, "longitude": -5.995},
              "km_from_start": 2.4, "description": "Views over Belfast Lough."},
        tests=[status(201), set_var("poi_id", "pm.response.json()._id")]),
    req("Add POI beyond trail end", "POST", "/trails/{{trail_id}}/pois",
        body={"name": "Too far", "type": "viewpoint", "location": {"latitude": 54.6, "longitude": -5.9},
              "km_from_start": 50},
        tests=[status(400), has_error()]),
    req("Add POI without token", "POST", "/trails/{{trail_id}}/pois", auth=None,
        body={"name": "No token", "type": "viewpoint", "location": {"latitude": 54.6, "longitude": -5.9}},
        tests=[status(401)]),
    req("List points of interest", "GET", "/trails/{{trail_id}}/pois", auth=None,
        tests=[status(200), 'pm.test("One POI", () => pm.expect(pm.response.json().count).to.eql(1));']),
    req("Update point of interest", "PATCH", "/trails/{{trail_id}}/pois/{{poi_id}}", body={"name": "Napoleon's Nose"},
        tests=[status(200), 'pm.test("Renamed", () => pm.expect(pm.response.json().name).to.eql("Napoleon\'s Nose"));']),
    req("Get point of interest", "GET", "/trails/{{trail_id}}/pois/{{poi_id}}", auth=None, tests=[status(200)]),
], "Points of interest are a sub-document collection embedded in each trail.")

reviews = folder("Reviews", [
    req("Add review", "POST", "/trails/{{trail_id}}/reviews",
        body={"rating": 4, "title": "Great evening walk", "comment": "Well-marked path with lovely views.",
              "hiked_on": "2026-06-14", "conditions": "dry"},
        tests=[status(201), set_var("review_id", "pm.response.json()._id")]),
    req("Trail rating recalculated", "GET", "/trails/{{trail_id}}", auth=None,
        tests=[status(200),
               'const t = pm.response.json();',
               'pm.test("Average rating updated", () => pm.expect(t.avg_rating).to.eql(4));',
               'pm.test("Review count updated", () => pm.expect(t.review_count).to.eql(1));']),
    req("Add second review (duplicate)", "POST", "/trails/{{trail_id}}/reviews",
        body={"rating": 2, "title": "Second go", "comment": "Trying to review the same trail twice.",
              "hiked_on": "2026-06-15"},
        tests=[status(409), has_error()]),
    req("Add review with invalid data", "POST", "/trails/{{trail_id}}/reviews",
        body={"rating": 9, "title": "x", "comment": "short", "hiked_on": "2999-01-01"},
        tests=[status(400),
               'pm.test("Field errors listed", () => pm.expect(pm.response.json().details).to.have.all.keys("rating", "title", "comment", "hiked_on"));']),
    req("List reviews for a seeded trail (sorted by helpfulness)", "GET", "/trails/{{seed_trail_id}}/reviews",
        auth=None, query={"sort": "helpful", "ps": 5},
        prerequest=[
            'pm.sendRequest(pm.collectionVariables.get("base_url") + "/trails?sort=review_count&order=desc&ps=1", (err, res) => {',
            '  pm.collectionVariables.set("seed_trail_id", res.json().data[0]._id);',
            '});'],
        tests=[status(200),
               'const c = pm.response.json().data.map(r => r.helpful_count);',
               'pm.test("Sorted by helpful votes", () => pm.expect(c).to.eql([...c].sort((a, b) => b - a)));']),
    req("Get one review", "GET", "/trails/{{trail_id}}/reviews/{{review_id}}", auth=None, tests=[status(200)]),
    req("Update own review", "PATCH", "/trails/{{trail_id}}/reviews/{{review_id}}", body={"rating": 5},
        tests=[status(200), 'pm.test("Rating changed", () => pm.expect(pm.response.json().rating).to.eql(5));']),
    req("Admin cannot edit someone else's review", "PATCH", "/trails/{{trail_id}}/reviews/{{review_id}}",
        auth="admin", body={"rating": 1}, tests=[status(403)]),
    req("Vote own review helpful", "POST", "/trails/{{trail_id}}/reviews/{{review_id}}/helpful", tests=[status(403)]),
    req("Another user votes review helpful", "POST", "/trails/{{trail_id}}/reviews/{{review_id}}/helpful",
        auth="admin",
        tests=[status(201), 'pm.test("Vote counted", () => pm.expect(pm.response.json().helpful_count).to.eql(1));']),
    req("Vote helpful twice", "POST", "/trails/{{trail_id}}/reviews/{{review_id}}/helpful", auth="admin",
        tests=[status(409)]),
], "Reviews are an embedded sub-document collection; ratings are recalculated with an aggregation.")

users = folder("Users", [
    req("Add trail to favourites", "PUT", "/users/me/favourites/{{trail_id}}", tests=[status(201)]),
    req("List favourites", "GET", "/users/me/favourites",
        tests=[status(200),
               'pm.test("Trail is a favourite", () => pm.expect(pm.response.json().data.map(t => t._id)).to.include(pm.collectionVariables.get("trail_id")));']),
    req("Log a completed hike", "POST", "/users/me/completed",
        body={"trail_id": "{{trail_id}}", "completed_on": "2026-06-14", "duration_mins": 95},
        tests=[status(201), set_var("entry_id", "pm.response.json()._id")]),
    req("List completed hikes", "GET", "/users/me/completed",
        tests=[status(200), 'pm.test("Trail details joined", () => pm.expect(pm.response.json().data[0].trail.name).to.eql("Postman Test Loop"));']),
    req("Personal hiking stats", "GET", "/users/me/stats",
        tests=[status(200),
               'const s = pm.response.json();',
               'pm.test("One hike logged", () => pm.expect(s.hikes_completed).to.eql(1));',
               'pm.test("Distance totalled", () => pm.expect(s.total_distance_km).to.eql(6.2));']),
    req("Update profile name", "PATCH", "/users/me", body={"name": "Renamed Hiker"},
        tests=[status(200), 'pm.test("Name updated", () => pm.expect(pm.response.json().name).to.eql("Renamed Hiker"));']),
    req("Change password without current password", "PATCH", "/users/me", body={"password": "Another123"},
        tests=[status(403)]),
    req("List users as hiker (forbidden)", "GET", "/users", tests=[status(403)]),
    req("List users as admin", "GET", "/users", auth="admin", query={"q": "hiker_", "ps": 5},
        tests=[status(200), 'pm.test("No password hashes exposed", () => pm.response.json().data.forEach(u => pm.expect(u).to.not.have.property("password")));']),
], "Profile management, favourites, completed-hike log and admin user management.")

stats = folder("Statistics", [
    req("Overview", "GET", "/stats/overview", auth=None,
        tests=[status(200), 'pm.test("Has trail count", () => pm.expect(pm.response.json().trails).to.be.above(0));']),
    req("By region", "GET", "/stats/regions", auth=None,
        tests=[status(200),
               'const c = pm.response.json().data.map(r => r.trail_count);',
               'pm.test("Sorted by trail count", () => pm.expect(c).to.eql([...c].sort((a, b) => b - a)));']),
    req("By difficulty", "GET", "/stats/difficulty", auth=None, tests=[status(200)]),
    req("Distance bands", "GET", "/stats/distance-bands", auth=None, tests=[status(200)]),
    req("Popular tags", "GET", "/stats/tags", auth=None, query={"limit": 5},
        tests=[status(200), 'pm.test("Five tags", () => pm.expect(pm.response.json().data.length).to.eql(5));']),
    req("Top rated", "GET", "/stats/top-rated", auth=None, query={"min_reviews": 5, "limit": 5},
        tests=[status(200), 'pm.test("Min reviews respected", () => pm.response.json().data.forEach(t => pm.expect(t.review_count).to.be.at.least(5)));']),
    req("Reviews by month", "GET", "/stats/reviews/monthly", auth=None, tests=[status(200)]),
    req("Conditions report", "GET", "/stats/conditions", auth=None, tests=[status(200)]),
], "Aggregation-pipeline analytics.")

cleanup = folder("Clean up", [
    req("Delete completed hike", "DELETE", "/users/me/completed/{{entry_id}}", tests=[status(204)]),
    req("Remove favourite", "DELETE", "/users/me/favourites/{{trail_id}}", tests=[status(204)]),
    req("Delete review", "DELETE", "/trails/{{trail_id}}/reviews/{{review_id}}", tests=[status(204)]),
    req("Delete point of interest", "DELETE", "/trails/{{trail_id}}/pois/{{poi_id}}", tests=[status(204)]),
    req("Delete trail", "DELETE", "/trails/{{trail_id}}", tests=[status(204)]),
    req("Deleted trail is gone", "GET", "/trails/{{trail_id}}", auth=None, tests=[status(404)]),
    req("Logout", "POST", "/auth/logout", tests=[status(200)]),
    req("Token rejected after logout", "GET", "/auth/me", tests=[status(401)]),
    req("Admin deletes test user", "DELETE", "/users/{{user_id}}", auth="admin", tests=[status(204)]),
], "Removes everything the run created so the collection can be run repeatedly.")

collection = {
    "info": {
        "name": "TrailBlazer API",
        "description": "Automated tests and documentation for the TrailBlazer hiking trails API "
                       "(COM661 CW1). Run the whole collection in order with the Collection Runner.",
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "item": [auth, trails, pois, reviews, users, stats, cleanup],
    "variable": [
        {"key": "base_url", "value": "http://127.0.0.1:5000/api/v1.0"},
        {"key": "password", "value": "Hiking2026"},
        {"key": "admin_password", "value": "AdminPass123"},
        {"key": "username", "value": ""},
        {"key": "user_id", "value": ""},
        {"key": "token", "value": ""},
        {"key": "admin_token", "value": ""},
        {"key": "trail_id", "value": ""},
        {"key": "seed_trail_id", "value": ""},
        {"key": "review_id", "value": ""},
        {"key": "poi_id", "value": ""},
        {"key": "entry_id", "value": ""},
    ],
}

if __name__ == "__main__":
    OUT.write_text(json.dumps(collection, indent=2) + "\n")
    count = sum(len(f["item"]) for f in collection["item"])
    print(f"Wrote {OUT} ({count} requests)")
