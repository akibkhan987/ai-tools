"""Test fixtures. Tests run against a real MongoDB using a separate `trailblazer_test` database."""
import os

import pytest
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError

from seed.build_dataset import ADMIN_PASSWORD, DEMO_PASSWORD
from seed.seed_db import seed
from trailblazer import create_app

TEST_DB = os.environ.get("MONGO_TEST_DB", "trailblazer_test")


@pytest.fixture(scope="session")
def mongo_db():
    client = MongoClient(os.environ.get("MONGO_URI", "mongodb://127.0.0.1:27017"),
                         serverSelectionTimeoutMS=3000, tz_aware=True)
    try:
        client.server_info()
    except ServerSelectionTimeoutError:
        pytest.exit("MongoDB is not reachable - start mongod before running the tests", returncode=1)
    db = client[TEST_DB]
    yield db
    client.drop_database(TEST_DB)


@pytest.fixture(scope="session")
def dataset(mongo_db):
    return seed(mongo_db)


@pytest.fixture(scope="session")
def app(mongo_db, dataset):
    return create_app(db=mongo_db, config_overrides={"TESTING": True, "SECRET_KEY": "x" * 64})


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, username, password):
    response = client.post("/api/v1/auth/login", auth=(username, password))
    assert response.status_code == 200, response.get_json()
    return {"x-access-token": response.get_json()["token"]}


@pytest.fixture
def admin_headers(client):
    return login(client, "admin", ADMIN_PASSWORD)


@pytest.fixture
def hiker(dataset):
    return dataset["users"][1]


@pytest.fixture
def hiker_headers(client, hiker):
    return login(client, hiker["username"], DEMO_PASSWORD)


_counter = {"n": 0}


@pytest.fixture
def new_user(client):
    """Register a brand-new user and return (user_json, auth_headers)."""
    _counter["n"] += 1
    username = f"tester_{os.getpid()}_{_counter['n']}"
    password = "Secret123"
    response = client.post("/api/v1/auth/register", json={
        "username": username, "email": f"{username}@example.com", "password": password, "name": "Test User"})
    assert response.status_code == 201, response.get_json()
    return response.get_json()["user"], login(client, username, password)


VALID_TRAIL = {
    "name": "Test Trail Loop",
    "description": "A pleasant test loop created by the automated test suite.",
    "region": "Test Region",
    "country": "Northern Ireland",
    "location": {"latitude": 54.6, "longitude": -5.9},
    "distance_km": 6.5,
    "elevation_gain_m": 210,
    "estimated_duration_mins": 120,
    "difficulty": "moderate",
    "route_type": "circular",
    "tags": ["Forest", "views", "forest"],
    "best_seasons": ["spring", "summer"],
    "features": {"dog_friendly": True, "parking": True},
}


@pytest.fixture
def make_trail(client):
    """Factory that creates a trail owned by the given user."""
    created = {"n": 0}

    def _make(headers, **overrides):
        created["n"] += 1
        body = {**VALID_TRAIL, "name": f"Test Trail {os.getpid()}-{id(created)}-{created['n']}", **overrides}
        response = client.post("/api/v1/trails", json=body, headers=headers)
        assert response.status_code == 201, response.get_json()
        return response.get_json()

    return _make
