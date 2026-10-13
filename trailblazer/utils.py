"""Shared helpers: JSON serialisation, error handling, ObjectId parsing and pagination."""
import math
from datetime import date, datetime

from bson import ObjectId
from flask import current_app, jsonify, make_response, request
from flask.json.provider import DefaultJSONProvider
from werkzeug.exceptions import HTTPException


class ApiJSONProvider(DefaultJSONProvider):
    """Serialise MongoDB types: ObjectId -> str, datetime -> ISO 8601."""

    @staticmethod
    def default(o):
        if isinstance(o, ObjectId):
            return str(o)
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        return DefaultJSONProvider.default(o)


class ApiError(Exception):
    """Raised anywhere in a request to return a JSON error with a status code."""

    def __init__(self, status, message, details=None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.details = details


def respond(body, status=200):
    return make_response(jsonify(body), status)


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def handle_api_error(err):
        body = {"error": err.message}
        if err.details:
            body["details"] = err.details
        return respond(body, err.status)

    @app.errorhandler(HTTPException)
    def handle_http_error(err):
        # Turns Flask's HTML 404/405/415 pages into JSON
        return respond({"error": err.description}, err.code)

    @app.errorhandler(Exception)
    def handle_unexpected(err):
        app.logger.exception("Unhandled error")
        return respond({"error": "Internal server error"}, 500)


def parse_object_id(value, label="ID"):
    """Convert a URL id to an ObjectId.

    As in the module's API design (BE03 Table 3.2), an id that is not valid is
    treated the same as one that doesn't exist: 404 Not Found.
    """
    if not ObjectId.is_valid(value):
        raise ApiError(404, f"Invalid {label}")
    return ObjectId(value)



def int_arg(name, default=None, minimum=None, maximum=None):
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ApiError(400, f"Query parameter '{name}' must be an integer")
    if minimum is not None and value < minimum:
        raise ApiError(400, f"Query parameter '{name}' must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ApiError(400, f"Query parameter '{name}' must be <= {maximum}")
    return value


def float_arg(name, default=None, minimum=None, maximum=None):
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ApiError(400, f"Query parameter '{name}' must be a number")
    if not math.isfinite(value):
        raise ApiError(400, f"Query parameter '{name}' must be a finite number")
    if minimum is not None and value < minimum:
        raise ApiError(400, f"Query parameter '{name}' must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ApiError(400, f"Query parameter '{name}' must be <= {maximum}")
    return value


def bool_arg(name):
    raw = request.args.get(name)
    if raw is None or raw == "":
        return None
    lowered = raw.lower()
    if lowered in ("true", "1", "yes"):
        return True
    if lowered in ("false", "0", "no"):
        return False
    raise ApiError(400, f"Query parameter '{name}' must be true or false")


def choice_arg(name, choices, default=None):
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default
    if raw not in choices:
        raise ApiError(400, f"Query parameter '{name}' must be one of: {', '.join(choices)}")
    return raw


def pagination_args():
    """Read `pn` (page number) and `ps` (page size) query parameters."""
    page = int_arg("pn", 1, minimum=1)
    size = int_arg("ps", current_app.config["DEFAULT_PAGE_SIZE"], minimum=1,
                   maximum=current_app.config["MAX_PAGE_SIZE"])
    return page, size


def paginated(items, total, page, size):
    """Paginated response format suggested in the module's API Development Hints."""
    return {
        "this_page": page,
        "number_of_pages": math.ceil(total / size) if total else 0,
        "page_size": size,
        "total": total,
        "data": items,
    }
