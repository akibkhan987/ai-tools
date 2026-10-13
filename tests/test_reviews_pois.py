from bson import ObjectId

REVIEW = {"rating": 4, "title": "Lovely walk", "comment": "Great views and a well-marked path.",
          "hiked_on": "2026-05-01", "conditions": "dry"}


def reviews_url(trail_id, review_id=None):
    url = f"/api/v1/trails/{trail_id}/reviews"
    return f"{url}/{review_id}" if review_id else url


def test_list_reviews_paginated_and_sorted(client, dataset):
    trail = max(dataset["trails"], key=lambda t: len(t["reviews"]))
    body = client.get(reviews_url(trail["_id"]) + "?ps=3&sort=highest").get_json()
    assert body["total"] == len(trail["reviews"])
    assert len(body["data"]) == 3
    ratings = [r["rating"] for r in body["data"]]
    assert ratings == sorted(ratings, reverse=True)
    helpful = client.get(reviews_url(trail["_id"]) + "?sort=helpful&ps=50").get_json()["data"]
    counts = [r["helpful_count"] for r in helpful]
    assert counts == sorted(counts, reverse=True)


def test_list_reviews_min_rating(client, dataset):
    trail = dataset["trails"][0]
    data = client.get(reviews_url(trail["_id"]) + "?min_rating=4&ps=50").get_json()["data"]
    assert all(r["rating"] >= 4 for r in data)


def test_review_lifecycle_updates_average(client, hiker_headers, new_user, make_trail):
    trail = make_trail(hiker_headers)
    _, other = new_user

    created = client.post(reviews_url(trail["_id"]), json=REVIEW, headers=other)
    assert created.status_code == 201
    review_id = created.get_json()["_id"]
    assert client.get(f"/api/v1/trails/{trail['_id']}").get_json()["avg_rating"] == 4

    # second review from the trail owner
    client.post(reviews_url(trail["_id"]), json={**REVIEW, "rating": 1}, headers=hiker_headers)
    detail = client.get(f"/api/v1/trails/{trail['_id']}").get_json()
    assert detail["avg_rating"] == 2.5 and detail["review_count"] == 2

    patched = client.patch(reviews_url(trail["_id"], review_id), json={"rating": 5}, headers=other)
    assert patched.status_code == 200 and patched.get_json()["rating"] == 5
    assert client.get(f"/api/v1/trails/{trail['_id']}").get_json()["avg_rating"] == 3

    assert client.delete(reviews_url(trail["_id"], review_id), headers=other).status_code == 204
    assert client.get(reviews_url(trail["_id"], review_id)).status_code == 404
    assert client.get(f"/api/v1/trails/{trail['_id']}").get_json()["avg_rating"] == 1


def test_one_review_per_user(client, hiker_headers, make_trail):
    trail = make_trail(hiker_headers)
    assert client.post(reviews_url(trail["_id"]), json=REVIEW, headers=hiker_headers).status_code == 201
    assert client.post(reviews_url(trail["_id"]), json=REVIEW, headers=hiker_headers).status_code == 409


def test_review_on_missing_trail(client, hiker_headers):
    assert client.post(reviews_url(ObjectId()), json=REVIEW, headers=hiker_headers).status_code == 404


def test_review_validation(client, hiker_headers, make_trail):
    trail = make_trail(hiker_headers)
    bad = {"rating": 6, "title": "x", "comment": "short", "hiked_on": "2999-01-01", "conditions": "lava"}
    response = client.post(reviews_url(trail["_id"]), json=bad, headers=hiker_headers)
    assert response.status_code == 400
    assert set(response.get_json()["details"]) == {"rating", "title", "comment", "hiked_on", "conditions"}


def test_cannot_edit_others_review_but_admin_can_delete(client, hiker_headers, admin_headers, new_user, make_trail):
    trail = make_trail(hiker_headers)
    review_id = client.post(reviews_url(trail["_id"]), json=REVIEW, headers=hiker_headers).get_json()["_id"]
    _, other = new_user
    url = reviews_url(trail["_id"], review_id)
    assert client.patch(url, json={"rating": 1}, headers=other).status_code == 403
    assert client.delete(url, headers=other).status_code == 403
    assert client.patch(url, json={"rating": 1}, headers=admin_headers).status_code == 403
    assert client.delete(url, headers=admin_headers).status_code == 204


def test_helpful_votes(client, hiker_headers, new_user, make_trail):
    trail = make_trail(hiker_headers)
    review_id = client.post(reviews_url(trail["_id"]), json=REVIEW, headers=hiker_headers).get_json()["_id"]
    url = reviews_url(trail["_id"], review_id) + "/helpful"
    _, other = new_user

    assert client.post(url, headers=hiker_headers).status_code == 403  # own review
    voted = client.post(url, headers=other)
    assert voted.status_code == 201 and voted.get_json()["helpful_count"] == 1
    assert client.post(url, headers=other).status_code == 409
    assert client.delete(url, headers=other).status_code == 204
    assert client.delete(url, headers=other).status_code == 404


POI = {"name": "Waterfall view", "type": "waterfall",
       "location": {"latitude": 54.61, "longitude": -5.91}, "km_from_start": 2.5}


def test_poi_crud(client, hiker_headers, make_trail):
    trail = make_trail(hiker_headers)
    base = f"/api/v1/trails/{trail['_id']}/pois"

    created = client.post(base, json=POI, headers=hiker_headers)
    assert created.status_code == 201
    poi_id = created.get_json()["_id"]
    client.post(base, json={**POI, "name": "Start car park", "type": "parking", "km_from_start": 0},
                headers=hiker_headers)

    listing = client.get(base).get_json()
    assert [p["km_from_start"] for p in listing["data"]] == [0, 2.5]
    assert client.get(base + "?type=parking").get_json()["count"] == 1

    patched = client.patch(f"{base}/{poi_id}", json={"name": "Big waterfall"}, headers=hiker_headers)
    assert patched.status_code == 200 and patched.get_json()["name"] == "Big waterfall"
    assert client.get(f"{base}/{poi_id}").get_json()["name"] == "Big waterfall"

    assert client.delete(f"{base}/{poi_id}", headers=hiker_headers).status_code == 204
    assert client.get(f"{base}/{poi_id}").status_code == 404


def test_poi_cannot_be_beyond_trail_end(client, hiker_headers, make_trail):
    trail = make_trail(hiker_headers)
    response = client.post(f"/api/v1/trails/{trail['_id']}/pois", json={**POI, "km_from_start": 99},
                           headers=hiker_headers)
    assert response.status_code == 400


def test_poi_requires_trail_owner(client, hiker_headers, new_user, make_trail):
    trail = make_trail(hiker_headers)
    _, other = new_user
    response = client.post(f"/api/v1/trails/{trail['_id']}/pois", json=POI, headers=other)
    assert response.status_code == 403
