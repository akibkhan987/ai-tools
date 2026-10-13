"""Account registration, login (token issue) and logout (token revocation)."""
from datetime import datetime, timezone

from flask import Blueprint, g, request
from pymongo.errors import DuplicateKeyError

from .. import db
from ..auth_utils import check_password, hash_password, issue_token, jwt_required
from ..utils import ApiError, get_json_body, respond
from ..validation import REGISTER_SCHEMA, check_password_strength, validate

auth_bp = Blueprint("auth", __name__)


def public_user(user):
    """Strip private fields before returning a user document."""
    return {k: v for k, v in user.items() if k != "password"}


@auth_bp.route("/auth/register", methods=["POST"])
def register():
    data = validate(get_json_body(), REGISTER_SCHEMA)
    check_password_strength(data["password"])
    data["username"] = data["username"].lower()
    data["email"] = data["email"].lower()

    if db.users().find_one({"$or": [{"username": data["username"]}, {"email": data["email"]}]}):
        raise ApiError(409, "Username or email is already registered")

    user = {
        **data,
        "password": hash_password(data["password"]),
        "admin": False,
        "favourites": [],
        "completed": [],
        "created_at": datetime.now(timezone.utc),
    }
    try:
        result = db.users().insert_one(user)
    except DuplicateKeyError:  # lost a race with a concurrent registration
        raise ApiError(409, "Username or email is already registered")
    user["_id"] = result.inserted_id
    return respond({"message": "Account created", "user": public_user(user)}, 201)


@auth_bp.route("/auth/login", methods=["POST"])
def login():
    """Log in with HTTP Basic Auth (as in the module) or a JSON body."""
    auth = request.authorization
    if auth and auth.username:
        username, password = auth.username, auth.password
    else:
        body = request.get_json(silent=True) or {}
        username, password = body.get("username"), body.get("password")

    if not isinstance(username, str) or not isinstance(password, str) or not username or not password:
        raise ApiError(401, "Username and password are required",
                       {"hint": "Use Basic Auth or a JSON body with 'username' and 'password'"})

    user = db.users().find_one({"username": username.lower()})
    # Same message for unknown user and wrong password so accounts can't be enumerated
    if user is None or not check_password(password, user["password"]):
        raise ApiError(401, "Invalid username or password")

    token, expires = issue_token(user)
    return respond({
        "token": token,
        "expires_at": expires,
        "user": {"_id": user["_id"], "username": user["username"], "admin": user.get("admin", False)},
    })


@auth_bp.route("/auth/logout", methods=["POST"])
@jwt_required
def logout():
    claims = g.token_claims
    db.blacklist().insert_one({
        "jti": claims["jti"],
        "user_id": g.user["_id"],
        "expires_at": datetime.fromtimestamp(claims["exp"], tz=timezone.utc),
    })
    return respond({"message": "Logged out"})


@auth_bp.route("/auth/me", methods=["GET"])
@jwt_required
def me():
    return respond(g.user)
