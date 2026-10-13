from seed.build_dataset import DEMO_PASSWORD


def test_register_creates_user_without_exposing_password(client):
    response = client.post("/api/v1.0/auth/register", json={
        "username": "New_Walker", "email": "New.Walker@Example.com", "password": "Walking123", "name": "New Walker"})
    assert response.status_code == 201
    user = response.get_json()["user"]
    assert user["username"] == "new_walker"
    assert user["email"] == "new.walker@example.com"
    assert "password" not in user
    assert user["admin"] is False


def test_register_rejects_duplicate_username(client, hiker):
    response = client.post("/api/v1.0/auth/register", json={
        "username": hiker["username"], "email": "other@example.com", "password": "Walking123", "name": "Dup"})
    assert response.status_code == 409


def test_register_reports_every_invalid_field(client):
    response = client.post("/api/v1.0/auth/register", json={
        "username": "a!", "email": "not-an-email", "password": "short", "extra": 1})
    assert response.status_code == 400
    details = response.get_json()["details"]
    assert set(details) == {"username", "email", "password", "name", "extra"}


def test_register_requires_letter_and_number_in_password(client):
    response = client.post("/api/v1.0/auth/register", json={
        "username": "weakpw", "email": "weak@example.com", "password": "onlyletters", "name": "Weak"})
    assert response.status_code == 400
    assert "password" in response.get_json()["details"]


def test_register_with_form_data(client):
    response = client.post("/api/v1.0/auth/register", data={
        "username": "form_walker", "email": "form@example.com", "password": "Walking123", "name": "Form Walker"})
    assert response.status_code == 201


def test_register_rejects_unsupported_body(client):
    response = client.post("/api/v1.0/auth/register", data="username=x", content_type="text/plain")
    assert response.status_code == 415


def test_login_with_basic_auth_and_json(client, hiker):
    basic = client.post("/api/v1.0/auth/login", auth=(hiker["username"], DEMO_PASSWORD))
    assert basic.status_code == 200
    assert basic.get_json()["token"]
    as_json = client.post("/api/v1.0/auth/login", json={"username": hiker["username"], "password": DEMO_PASSWORD})
    assert as_json.status_code == 200
    as_form = client.post("/api/v1.0/auth/login", data={"username": hiker["username"], "password": DEMO_PASSWORD})
    assert as_form.status_code == 200


def test_login_wrong_password_and_unknown_user_look_the_same(client, hiker):
    wrong = client.post("/api/v1.0/auth/login", auth=(hiker["username"], "nope"))
    unknown = client.post("/api/v1.0/auth/login", auth=("nobody_here", "nope"))
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.get_json() == unknown.get_json()


def test_login_without_credentials(client):
    assert client.post("/api/v1.0/auth/login").status_code == 401


def test_protected_route_requires_token(client):
    assert client.get("/api/v1.0/auth/me").status_code == 401
    bad = client.get("/api/v1.0/auth/me", headers={"x-access-token": "garbage"})
    assert bad.status_code == 401


def test_bearer_header_is_accepted(client, hiker_headers):
    token = hiker_headers["x-access-token"]
    response = client.get("/api/v1.0/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


def test_logout_revokes_token(client, new_user):
    _, headers = new_user
    assert client.get("/api/v1.0/auth/me", headers=headers).status_code == 200
    assert client.post("/api/v1.0/auth/logout", headers=headers).status_code == 200
    response = client.get("/api/v1.0/auth/me", headers=headers)
    assert response.status_code == 401
    assert "revoked" in response.get_json()["error"]
