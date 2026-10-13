"""JWT token handling, password hashing and access-control decorators."""
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps

import bcrypt
import jwt
from bson import ObjectId
from flask import current_app, g, request

from . import db
from .utils import ApiError

ALGORITHM = "HS256"


def hash_password(plain):
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def check_password(plain, hashed):
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def issue_token(user):
    expires = datetime.now(timezone.utc) + timedelta(minutes=current_app.config["TOKEN_LIFETIME_MINUTES"])
    payload = {
        "sub": str(user["_id"]),
        "username": user["username"],
        "admin": user.get("admin", False),
        "jti": uuid.uuid4().hex,  # unique id so a single token can be revoked on logout
        "exp": expires,
    }
    return jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm=ALGORITHM), expires


def read_token_from_request():
    """Accept the module's `x-access-token` header or a standard Bearer header."""
    token = request.headers.get("x-access-token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[len("Bearer "):].strip()
    return token


def decode_token(token):
    try:
        return jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise ApiError(401, "Token has expired, please log in again")
    except jwt.InvalidTokenError:
        raise ApiError(401, "Token is invalid")


def jwt_required(func):
    """Reject the request unless it carries a valid, non-revoked token for an existing user."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        token = read_token_from_request()
        if not token:
            raise ApiError(401, "Authentication token is missing")
        claims = decode_token(token)
        if db.blacklist().find_one({"jti": claims.get("jti")}):
            raise ApiError(401, "Token has been revoked, please log in again")
        user = db.users().find_one({"_id": _object_id(claims.get("sub"))}, {"password": 0})
        if user is None:
            raise ApiError(401, "User for this token no longer exists")
        g.user = user
        g.token_claims = claims
        return func(*args, **kwargs)

    return wrapper


def admin_required(func):
    """Must be applied *after* (i.e. listed below) @jwt_required."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        if not g.user.get("admin", False):
            raise ApiError(403, "Admin access required")
        return func(*args, **kwargs)

    return wrapper


def is_admin():
    return bool(g.get("user") and g.user.get("admin", False))


def _object_id(value):
    return ObjectId(value) if value and ObjectId.is_valid(value) else None
