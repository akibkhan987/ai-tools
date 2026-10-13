"""Declarative request-body validation.

Each schema maps a field name to a `Field` describing its type and constraints.
`validate()` returns a cleaned dict ready for MongoDB, or raises a 400 ApiError
listing every problem found (rather than stopping at the first one).

Request bodies can be sent either as form data (x-www-form-urlencoded or
form-data, as used with request.form in the module practicals) or as JSON.
Form values always arrive as strings, so `form_to_payload()` converts them to
the types the schema expects before validation.
"""
import math
import re
from datetime import date, datetime, timezone

from flask import request

from .utils import ApiError

DIFFICULTIES = ["easy", "moderate", "hard", "strenuous"]
ROUTE_TYPES = ["circular", "linear", "out-and-back"]
SEASONS = ["spring", "summer", "autumn", "winter"]
CONDITIONS = ["dry", "muddy", "wet", "snow", "ice", "windy"]
POI_TYPES = ["summit", "viewpoint", "waterfall", "lake", "historic", "wildlife", "refreshments", "parking", "shelter"]
FEATURE_KEYS = ["dog_friendly", "wheelchair_accessible", "parking", "public_transport", "toilets", "cafe"]

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
URL_RE = re.compile(r"^https?://\S+$")


class Field:
    def __init__(self, kind, required=False, min_value=None, max_value=None,
                 min_len=None, max_len=None, choices=None, pattern=None, item_choices=None,
                 max_items=None, message=None):
        self.kind = kind
        self.required = required
        self.min_value = min_value
        self.max_value = max_value
        self.min_len = min_len
        self.max_len = max_len
        self.choices = choices
        self.pattern = pattern
        self.item_choices = item_choices
        self.max_items = max_items
        self.message = message

    def clean(self, value):
        """Return the cleaned value or raise ValueError with a readable message."""
        cleaner = getattr(self, f"_clean_{self.kind}")
        return cleaner(value)

    def _check_range(self, value):
        if self.min_value is not None and value < self.min_value:
            raise ValueError(f"must be at least {self.min_value}")
        if self.max_value is not None and value > self.max_value:
            raise ValueError(f"must be at most {self.max_value}")
        return value

    def _clean_str(self, value):
        if not isinstance(value, str):
            raise ValueError("must be a string")
        value = value.strip()
        if self.min_len is not None and len(value) < self.min_len:
            raise ValueError(f"must be at least {self.min_len} characters")
        if self.max_len is not None and len(value) > self.max_len:
            raise ValueError(f"must be at most {self.max_len} characters")
        if self.choices and value not in self.choices:
            raise ValueError(f"must be one of: {', '.join(self.choices)}")
        if self.pattern and not self.pattern.match(value):
            raise ValueError(self.message or "has an invalid format")
        return value

    def _clean_int(self, value):
        # bool is a subclass of int in Python, so reject it explicitly
        if isinstance(value, bool) or not isinstance(value, int):
            if isinstance(value, float) and value.is_integer():
                value = int(value)
            else:
                raise ValueError("must be an integer")
        return self._check_range(value)

    def _clean_number(self, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("must be a number")
        return self._check_range(round(float(value), 2))

    def _clean_bool(self, value):
        if not isinstance(value, bool):
            raise ValueError("must be true or false")
        return value

    def _clean_str_list(self, value):
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ValueError("must be an array of strings")
        cleaned = []
        for item in value:
            item = item.strip().lower()
            if not item:
                raise ValueError("must not contain empty strings")
            if self.item_choices and item not in self.item_choices:
                raise ValueError(f"items must be from: {', '.join(self.item_choices)}")
            if item not in cleaned:  # de-duplicate, preserve order
                cleaned.append(item)
        if self.max_items is not None and len(cleaned) > self.max_items:
            raise ValueError(f"must contain at most {self.max_items} items")
        return cleaned

    def _clean_date(self, value):
        if not isinstance(value, str):
            raise ValueError("must be a date string in YYYY-MM-DD format")
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            raise ValueError("must be a date string in YYYY-MM-DD format")
        if parsed.date() > date.today():
            raise ValueError("must not be in the future")
        return parsed

    def _clean_location(self, value):
        """Accept {"latitude": .., "longitude": ..} and convert to a GeoJSON Point."""
        if not isinstance(value, dict):
            raise ValueError("must be an object with 'latitude' and 'longitude'")
        lat, lng = value.get("latitude"), value.get("longitude")
        for name, v in (("latitude", lat), ("longitude", lng)):
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise ValueError(f"'{name}' must be a number")
        if not -90 <= lat <= 90:
            raise ValueError("'latitude' must be between -90 and 90")
        if not -180 <= lng <= 180:
            raise ValueError("'longitude' must be between -180 and 180")
        # GeoJSON stores coordinates as [longitude, latitude]
        return {"type": "Point", "coordinates": [round(float(lng), 6), round(float(lat), 6)]}

    def _clean_features(self, value):
        if not isinstance(value, dict):
            raise ValueError("must be an object of true/false flags")
        unknown = [k for k in value if k not in FEATURE_KEYS]
        if unknown:
            raise ValueError(f"unknown feature(s): {', '.join(unknown)}; allowed: {', '.join(FEATURE_KEYS)}")
        for k, v in value.items():
            if not isinstance(v, bool):
                raise ValueError(f"'{k}' must be true or false")
        return dict(value)


def validate(payload, schema, partial=False):
    """Validate `payload` against `schema`.

    With partial=True (used by PATCH-style updates) missing required fields are
    allowed, but at least one known field must be supplied.
    """
    errors = {}
    cleaned = {}

    unknown = sorted(set(payload) - set(schema))
    for key in unknown:
        errors[key] = "is not an allowed field"

    for name, field in schema.items():
        if name not in payload or payload[name] is None:
            if field.required and not partial:
                errors[name] = "is required"
            continue
        try:
            cleaned[name] = field.clean(payload[name])
        except ValueError as exc:
            errors[name] = str(exc)

    if partial and not cleaned and not errors:
        raise ApiError(400, "No updatable fields supplied", {"allowed_fields": sorted(schema)})
    if errors:
        raise ApiError(400, "Validation failed", errors)
    return cleaned


def _to_number(value, kind):
    """Convert a form string to int/float; leave it unchanged if it isn't numeric
    so that validation reports a helpful 'must be a number' message."""
    try:
        number = int(value) if kind == "int" else float(value)
    except (TypeError, ValueError):
        return value
    return number if math.isfinite(number) else value


def _to_bool(value):
    lowered = str(value).strip().lower()
    if lowered in ("true", "1", "yes", "on"):
        return True
    if lowered in ("false", "0", "no", "off"):
        return False
    return value


def form_to_payload(form, schema):
    """Turn request.form (all strings) into the typed payload `validate()` expects.

    - numbers and booleans are converted from text
    - lists accept comma-separated text ("forest,views") or a repeated key
    - a location is sent as separate `latitude` and `longitude` fields
    - trail features are sent as individual flags, e.g. dog_friendly=true
    """
    payload = {}
    consumed = set()
    for name, field in schema.items():
        if field.kind == "location":
            if "latitude" in form or "longitude" in form:
                payload[name] = {"latitude": _to_number(form.get("latitude"), "number"),
                                 "longitude": _to_number(form.get("longitude"), "number")}
                consumed |= {"latitude", "longitude"}
        elif field.kind == "features":
            flags = {key: _to_bool(form[key]) for key in FEATURE_KEYS if key in form}
            if flags:
                payload[name] = flags
                consumed |= set(flags)
        elif name in form:
            consumed.add(name)
            if field.kind == "str_list":
                payload[name] = [part for raw in form.getlist(name) for part in raw.split(",") if part.strip()]
            elif field.kind in ("int", "number"):
                payload[name] = _to_number(form[name], field.kind)
            elif field.kind == "bool":
                payload[name] = _to_bool(form[name])
            else:
                payload[name] = form[name]
    # Anything left over is passed through so unknown fields are still reported
    for key in form:
        if key not in consumed:
            payload[key] = form[key]
    return payload


def read_body(schema):
    """Return the request body as a dict, from either form data or JSON."""
    if request.is_json:
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ApiError(400, "Request body must be a valid JSON object")
        return dict(body)
    if request.mimetype in ("application/x-www-form-urlencoded", "multipart/form-data"):
        return form_to_payload(request.form, schema)
    raise ApiError(415, "Send the request body as form data (x-www-form-urlencoded) or JSON")


def validate_request(schema, partial=False):
    """Read the request body and validate it against `schema` in one step."""
    return validate(read_body(schema), schema, partial=partial)


TRAIL_SCHEMA = {
    "name": Field("str", required=True, min_len=3, max_len=120),
    "description": Field("str", required=True, min_len=10, max_len=2000),
    "region": Field("str", required=True, min_len=2, max_len=80),
    "country": Field("str", required=True, choices=["England", "Scotland", "Wales", "Northern Ireland", "Ireland"]),
    "location": Field("location", required=True),
    "distance_km": Field("number", required=True, min_value=0.1, max_value=500),
    "elevation_gain_m": Field("int", required=True, min_value=0, max_value=9000),
    "estimated_duration_mins": Field("int", required=True, min_value=5, max_value=7 * 24 * 60),
    "difficulty": Field("str", required=True, choices=DIFFICULTIES),
    "route_type": Field("str", required=True, choices=ROUTE_TYPES),
    "tags": Field("str_list", max_items=15),
    "best_seasons": Field("str_list", item_choices=SEASONS),
    "features": Field("features"),
    "image_url": Field("str", max_len=500, pattern=URL_RE, message="must be an http(s) URL"),
}

REVIEW_SCHEMA = {
    "rating": Field("int", required=True, min_value=1, max_value=5),
    "title": Field("str", required=True, min_len=3, max_len=100),
    "comment": Field("str", required=True, min_len=10, max_len=2000),
    "hiked_on": Field("date", required=True),
    "conditions": Field("str", choices=CONDITIONS),
}

POI_SCHEMA = {
    "name": Field("str", required=True, min_len=2, max_len=100),
    "type": Field("str", required=True, choices=POI_TYPES),
    "location": Field("location", required=True),
    "description": Field("str", max_len=500),
    "km_from_start": Field("number", min_value=0, max_value=500),
}

REGISTER_SCHEMA = {
    "username": Field("str", required=True, pattern=USERNAME_RE,
                      message="must be 3-30 characters: letters, numbers or underscore"),
    "email": Field("str", required=True, max_len=254, pattern=EMAIL_RE, message="must be a valid email address"),
    "password": Field("str", required=True, min_len=8, max_len=72),
    "name": Field("str", required=True, min_len=1, max_len=100),
}

PROFILE_SCHEMA = {
    "email": REGISTER_SCHEMA["email"],
    "password": REGISTER_SCHEMA["password"],
    "name": REGISTER_SCHEMA["name"],
}

ROLE_SCHEMA = {
    "admin": Field("bool", required=True),
}

COMPLETION_SCHEMA = {
    "trail_id": Field("str", required=True, min_len=24, max_len=24),
    "completed_on": Field("date", required=True),
    "duration_mins": Field("int", min_value=5, max_value=7 * 24 * 60),
}


def check_password_strength(password):
    if not (re.search(r"[A-Za-z]", password) and re.search(r"\d", password)):
        raise ApiError(400, "Validation failed", {"password": "must contain at least one letter and one number"})
