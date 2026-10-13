from bson import ObjectId

from .conftest import VALID_TRAIL


def test_list_trails_is_paginated(client):
    response = client.get("/api/v1/trails?pn=2&ps=5")
    body = response.get_json()
    assert response.status_code == 200
    assert body["page"] == 2 and body["page_size"] == 5
    assert len(body["data"]) == 5
    assert body["total_pages"] == -(-body["total"] // 5)
    assert "reviews" not in body["data"][0]


def test_pages_do_not_overlap(client):
    first = {t["_id"] for t in client.get("/api/v1/trails?pn=1&ps=10").get_json()["data"]}
    second = {t["_id"] for t in client.get("/api/v1/trails?pn=2&ps=10").get_json()["data"]}
    assert first.isdisjoint(second)


def test_invalid_pagination(client):
    assert client.get("/api/v1/trails?pn=0").status_code == 400
    assert client.get("/api/v1/trails?ps=500").status_code == 400
    assert client.get("/api/v1/trails?pn=abc").status_code == 400


def test_filter_by_difficulty_and_distance(client):
    data = client.get("/api/v1/trails?difficulty=easy,moderate&max_distance=8&ps=50").get_json()["data"]
    assert data
    assert all(t["difficulty"] in ("easy", "moderate") and t["distance_km"] <= 8 for t in data)


def test_filter_by_tags_all_vs_any(client):
    any_tags = client.get("/api/v1/trails?tags=waterfall,coastal&ps=50").get_json()["total"]
    all_tags = client.get("/api/v1/trails?tags=coastal,cliffs&tag_match=all&ps=50").get_json()
    assert any_tags > 0
    assert all({"coastal", "cliffs"} <= set(t["tags"]) for t in all_tags["data"])


def test_filter_by_feature_flag_and_rating(client):
    data = client.get("/api/v1/trails?dog_friendly=false&ps=50").get_json()["data"]
    assert data and all(t["features"]["dog_friendly"] is False for t in data)
    rated = client.get("/api/v1/trails?min_rating=4.5&ps=50").get_json()["data"]
    assert all(t["avg_rating"] >= 4.5 for t in rated)


def test_text_search_is_case_insensitive_and_regex_safe(client):
    data = client.get("/api/v1/trails?q=CAUSEWAY").get_json()["data"]
    assert any("Causeway" in t["name"] for t in data)
    assert client.get("/api/v1/trails?q=.*(").status_code == 200


def test_sorting(client):
    data = client.get("/api/v1/trails?sort=distance_km&order=desc&ps=10").get_json()["data"]
    distances = [t["distance_km"] for t in data]
    assert distances == sorted(distances, reverse=True)
    assert client.get("/api/v1/trails?sort=password").status_code == 400


def test_invalid_filter_values(client):
    assert client.get("/api/v1/trails?difficulty=extreme").status_code == 400
    assert client.get("/api/v1/trails?min_distance=10&max_distance=5").status_code == 400
    assert client.get("/api/v1/trails?dog_friendly=maybe").status_code == 400


def test_get_single_trail_includes_latest_reviews(client, dataset):
    trail = dataset["trails"][0]
    body = client.get(f"/api/v1/trails/{trail['_id']}").get_json()
    assert body["name"] == trail["name"]
    assert len(body["latest_reviews"]) == min(3, len(trail["reviews"]))
    assert body["points_of_interest"]


def test_get_trail_bad_and_missing_id(client):
    assert client.get("/api/v1/trails/not-an-id").status_code == 400
    assert client.get(f"/api/v1/trails/{ObjectId()}").status_code == 404


def test_create_trail_cleans_data(client, hiker_headers):
    response = client.post("/api/v1/trails", json=VALID_TRAIL, headers=hiker_headers)
    assert response.status_code == 201
    trail = response.get_json()
    assert response.headers["Location"].endswith(trail["_id"])
    assert trail["location"] == {"type": "Point", "coordinates": [-5.9, 54.6]}
    assert trail["tags"] == ["forest", "views"]
    assert trail["features"]["dog_friendly"] is True and trail["features"]["cafe"] is False
    assert trail["avg_rating"] == 0 and trail["review_count"] == 0


def test_create_trail_requires_login(client):
    assert client.post("/api/v1/trails", json=VALID_TRAIL).status_code == 401


def test_create_duplicate_trail_in_region(client, hiker_headers, make_trail):
    trail = make_trail(hiker_headers)
    response = client.post("/api/v1/trails", json={**VALID_TRAIL, "name": trail["name"].upper()},
                           headers=hiker_headers)
    assert response.status_code == 409


def test_create_trail_validation(client, hiker_headers):
    bad = {**VALID_TRAIL, "distance_km": "far", "difficulty": "extreme", "elevation_gain_m": True,
           "location": {"latitude": 123, "longitude": 0}, "image_url": "ftp://x", "features": {"jetpack": True}}
    response = client.post("/api/v1/trails", json=bad, headers=hiker_headers)
    assert response.status_code == 400
    assert set(response.get_json()["details"]) >= {
        "distance_km", "difficulty", "elevation_gain_m", "location", "image_url", "features"}


def test_put_requires_all_fields_but_patch_does_not(client, hiker_headers, make_trail):
    trail = make_trail(hiker_headers)
    url = f"/api/v1/trails/{trail['_id']}"
    assert client.put(url, json={"distance_km": 7}, headers=hiker_headers).status_code == 400
    patched = client.patch(url, json={"distance_km": 7, "features": {"cafe": True}}, headers=hiker_headers)
    assert patched.status_code == 200
    body = patched.get_json()
    assert body["distance_km"] == 7
    # PATCHing one feature keeps the others
    assert body["features"]["cafe"] is True and body["features"]["dog_friendly"] is True
    full = {**VALID_TRAIL, "name": trail["name"], "difficulty": "hard"}
    assert client.put(url, json=full, headers=hiker_headers).get_json()["difficulty"] == "hard"


def test_patch_with_no_fields(client, hiker_headers, make_trail):
    trail = make_trail(hiker_headers)
    response = client.patch(f"/api/v1/trails/{trail['_id']}", json={}, headers=hiker_headers)
    assert response.status_code == 400


def test_only_owner_or_admin_can_modify(client, hiker_headers, admin_headers, new_user, make_trail):
    trail = make_trail(hiker_headers)
    url = f"/api/v1/trails/{trail['_id']}"
    _, other = new_user
    assert client.patch(url, json={"distance_km": 3}, headers=other).status_code == 403
    assert client.delete(url, headers=other).status_code == 403
    assert client.patch(url, json={"distance_km": 3}, headers=admin_headers).status_code == 200


def test_delete_trail_cleans_up_favourites(client, hiker_headers, make_trail):
    trail = make_trail(hiker_headers)
    client.put(f"/api/v1/users/me/favourites/{trail['_id']}", headers=hiker_headers)
    assert client.delete(f"/api/v1/trails/{trail['_id']}", headers=hiker_headers).status_code == 204
    assert client.get(f"/api/v1/trails/{trail['_id']}").status_code == 404
    favourites = client.get("/api/v1/users/me/favourites", headers=hiker_headers).get_json()["data"]
    assert trail["_id"] not in [f["_id"] for f in favourites]


def test_nearby_returns_sorted_distances(client):
    response = client.get("/api/v1/trails/nearby?lat=54.18&lng=-5.92&radius_km=30")
    body = response.get_json()
    assert response.status_code == 200 and body["count"] > 0
    distances = [t["distance_km"] for t in body["data"]]
    assert distances == sorted(distances)
    assert all(d <= 30 for d in distances)
    assert all(t["region"] == "Mourne Mountains" for t in body["data"])


def test_nearby_with_difficulty_and_validation(client):
    data = client.get("/api/v1/trails/nearby?lat=54.18&lng=-5.92&radius_km=30&difficulty=easy").get_json()["data"]
    assert all(t["difficulty"] == "easy" for t in data)
    assert client.get("/api/v1/trails/nearby?lat=54").status_code == 400
    assert client.get("/api/v1/trails/nearby?lat=95&lng=0").status_code == 400


def test_trails_near_a_trail_excludes_itself(client, dataset):
    trail = next(t for t in dataset["trails"] if t["name"].startswith("Giant's Causeway Red"))
    body = client.get(f"/api/v1/trails/{trail['_id']}/nearby?radius_km=30").get_json()
    ids = [t["_id"] for t in body["data"]]
    assert str(trail["_id"]) not in ids
    assert any("Carrick-a-Rede" in t["name"] for t in body["data"])


def test_unknown_route_and_method_return_json(client):
    missing = client.get("/api/v1/nothing-here")
    assert missing.status_code == 404 and "error" in missing.get_json()
    assert client.post("/api/v1/stats/overview").status_code == 405
