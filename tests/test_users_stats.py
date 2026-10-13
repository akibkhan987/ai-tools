from bson import ObjectId


def test_admin_can_list_users_but_hiker_cannot(client, admin_headers, hiker_headers):
    response = client.get("/api/v1.0/users?ps=5", headers=admin_headers)
    assert response.status_code == 200
    assert all("password" not in u for u in response.get_json()["data"])
    assert client.get("/api/v1.0/users", headers=hiker_headers).status_code == 403


def test_user_can_view_self_but_not_others(client, hiker, hiker_headers, dataset):
    assert client.get(f"/api/v1.0/users/{hiker['_id']}", headers=hiker_headers).status_code == 200
    other = dataset["users"][2]
    assert client.get(f"/api/v1.0/users/{other['_id']}", headers=hiker_headers).status_code == 403


def test_update_profile(client, new_user):
    _, headers = new_user
    renamed = client.patch("/api/v1.0/users/me", json={"name": "Renamed"}, headers=headers)
    assert renamed.status_code == 200 and renamed.get_json()["name"] == "Renamed"
    # changing the password needs the current one
    assert client.patch("/api/v1.0/users/me", json={"password": "NewPass123"}, headers=headers).status_code == 403
    ok = client.patch("/api/v1.0/users/me", json={"password": "NewPass123", "current_password": "Secret123"},
                      headers=headers)
    assert ok.status_code == 200


def test_favourites(client, new_user, dataset):
    _, headers = new_user
    trail_id = str(dataset["trails"][3]["_id"])
    assert client.put(f"/api/v1.0/users/me/favourites/{trail_id}", headers=headers).status_code == 201
    assert client.put(f"/api/v1.0/users/me/favourites/{trail_id}", headers=headers).status_code == 200
    favourites = client.get("/api/v1.0/users/me/favourites", headers=headers).get_json()
    assert favourites["count"] == 1 and favourites["data"][0]["_id"] == trail_id
    assert client.delete(f"/api/v1.0/users/me/favourites/{trail_id}", headers=headers).status_code == 204
    assert client.delete(f"/api/v1.0/users/me/favourites/{trail_id}", headers=headers).status_code == 404
    assert client.put(f"/api/v1.0/users/me/favourites/{ObjectId()}", headers=headers).status_code == 404


def test_completed_log_and_stats(client, new_user, dataset):
    _, headers = new_user
    empty = client.get("/api/v1.0/users/me/stats", headers=headers).get_json()
    assert empty["hikes_completed"] == 0

    a, b = dataset["trails"][0], dataset["trails"][1]
    for trail, day in ((a, "2026-03-01"), (b, "2026-04-01"), (a, "2026-05-01")):
        response = client.post("/api/v1.0/users/me/completed",
                               json={"trail_id": str(trail["_id"]), "completed_on": day}, headers=headers)
        assert response.status_code == 201

    log = client.get("/api/v1.0/users/me/completed", headers=headers).get_json()
    assert log["count"] == 3
    assert log["data"][0]["completed_on"].startswith("2026-05-01")

    stats = client.get("/api/v1.0/users/me/stats", headers=headers).get_json()
    assert stats["hikes_completed"] == 3
    assert stats["unique_trails"] == 2
    assert stats["total_distance_km"] == round(2 * a["distance_km"] + b["distance_km"], 2)

    entry_id = log["data"][0]["_id"]
    assert client.delete(f"/api/v1.0/users/me/completed/{entry_id}", headers=headers).status_code == 204
    assert client.delete(f"/api/v1.0/users/me/completed/{entry_id}", headers=headers).status_code == 404


def test_completed_validation(client, new_user):
    _, headers = new_user
    response = client.post("/api/v1.0/users/me/completed", json={"trail_id": "abc", "completed_on": "yesterday"},
                           headers=headers)
    assert response.status_code == 400


def test_deleting_user_removes_reviews_and_fixes_rating(client, hiker_headers, new_user, admin_headers, make_trail):
    trail = make_trail(hiker_headers)
    user, headers = new_user
    client.post(f"/api/v1.0/trails/{trail['_id']}/reviews", headers=headers, json={
        "rating": 2, "title": "Meh walk", "comment": "Not my favourite route.", "hiked_on": "2026-01-01"})
    assert client.get(f"/api/v1.0/trails/{trail['_id']}").get_json()["review_count"] == 1

    assert client.delete(f"/api/v1.0/users/{user['_id']}", headers=admin_headers).status_code == 204
    detail = client.get(f"/api/v1.0/trails/{trail['_id']}").get_json()
    assert detail["review_count"] == 0 and detail["avg_rating"] == 0
    assert client.get("/api/v1.0/auth/me", headers=headers).status_code == 401


def test_set_role(client, admin_headers, new_user):
    user, headers = new_user
    url = f"/api/v1.0/users/{user['_id']}/role"
    assert client.patch(url, json={"admin": True}, headers=headers).status_code == 403
    response = client.patch(url, json={"admin": True}, headers=admin_headers)
    assert response.status_code == 200 and response.get_json()["admin"] is True
    assert client.patch(url, json={"admin": "yes"}, headers=admin_headers).status_code == 400
    revoked = client.patch(url, data={"admin": "false"}, headers=admin_headers)
    assert revoked.status_code == 200 and revoked.get_json()["admin"] is False


def test_stats_endpoints(client, dataset):
    overview = client.get("/api/v1.0/stats/overview").get_json()
    assert overview["trails"] >= len(dataset["trails"])

    regions = client.get("/api/v1.0/stats/regions").get_json()["data"]
    counts = [r["trail_count"] for r in regions]
    assert counts == sorted(counts, reverse=True)

    difficulty = [d["difficulty"] for d in client.get("/api/v1.0/stats/difficulty").get_json()["data"]]
    assert difficulty[:4] == ["easy", "moderate", "hard", "strenuous"]

    bands = client.get("/api/v1.0/stats/distance-bands").get_json()["data"]
    assert sum(b["trail_count"] for b in bands) == overview["trails"]

    top = client.get("/api/v1.0/stats/top-rated?min_reviews=5&limit=5").get_json()["data"]
    assert len(top) <= 5 and all(t["review_count"] >= 5 for t in top)

    tags = client.get("/api/v1.0/stats/tags?limit=3").get_json()["data"]
    assert len(tags) == 3

    assert client.get("/api/v1.0/stats/reviews/monthly").get_json()["data"]
    assert client.get("/api/v1.0/stats/conditions").get_json()["data"]
