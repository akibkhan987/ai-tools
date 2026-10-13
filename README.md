# TrailBlazer API

A RESTful back end for discovering, reviewing and logging hikes across the UK and Ireland, built with **Python Flask** and **MongoDB** for COM661 Full Stack Strategies and Development, Coursework 1.

The API lets you:

- find trails by location, difficulty, distance, tags, facilities or rating;
- read and write reviews, and vote reviews helpful;
- add points of interest along a route;
- keep favourites and a log of completed hikes, with personal stats;
- look at aggregated statistics across the dataset.

## Features at a glance

| Area | What's included |
|---|---|
| Dataset | 45 real UK & Ireland walks (11 in Northern Ireland), 332 reviews, 91 points of interest, 25 users |
| Data types | strings, ints, floats, booleans, dates, arrays, nested objects, **GeoJSON** points |
| Sub-documents | `reviews[]` and `points_of_interest[]` inside each trail; `completed[]` log inside each user |
| CRUD | Full create/read/update/delete on trails, reviews, POIs, favourites, completed hikes and users |
| Queries | Multi-field filtering, `$in`/`$all` array matching, range queries, case-insensitive search, sorting, pagination |
| Geospatial | `2dsphere` index with `$geoNear`: trails near a point and trails near a trail |
| Aggregation | `$group`, `$unwind`, `$lookup`, `$facet`, `$bucket`, `$replaceRoot`, `$addToSet`, date operators |
| Auth | Registration, bcrypt hashing, JWT login (Basic Auth), logout via token blacklist (TTL index), admin role, owner-only edits |
| Validation | Every body field is type- and range-checked; all errors are reported together; JSON errors for every status code |
| Testing | 59 pytest tests and a 68-request Postman collection with 142 assertions |

## Project structure

```
app.py                          Entry point (python app.py)
trailblazer/
  __init__.py                   Application factory: config, DB connection, blueprints
  config.py                     Settings from environment variables
  db.py                         Collection helpers + index definitions
  decorators.py                 @jwt_required, @admin_required, bcrypt + JWT helpers
  validation.py                 Reads form or JSON bodies and validates them against schemas
  utils.py                      JSON encoding, error handling, query-string parsing, pagination
  blueprints/
    auth/auth.py                /auth/register, /auth/login, /auth/logout, /auth/me
    trails/trails.py            /trails CRUD, filtering, geo search
    reviews/reviews.py          /trails/<id>/reviews sub-document CRUD + helpful votes
    pois/pois.py                /trails/<id>/pois sub-document CRUD
    users/users.py              /users admin, profile, favourites, completed log, stats
    stats/stats.py              /stats aggregation endpoints
seed/
  trails_source.py              Hand-curated trail data
  build_dataset.py              Generates users, reviews, votes and activity (deterministic)
  seed_db.py                    Loads the dataset into MongoDB and creates indexes
tests/                          pytest suite (runs against a real MongoDB test database)
postman/
  build_collection.py           Generates the Postman collection
  TrailBlazer.postman_collection.json
docs/
  API_ENDPOINTS.md              Summary of every endpoint
  DESIGN.md                     Design & development notes
scripts/
  export_collections.sh         mongoexport each collection for submission
  make_code_listing.py          Builds the code-listing PDF
```

## Getting started

Requirements: Python 3.10+ and MongoDB 5.0+ running locally.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m seed.seed_db             # load the dataset into the 'trailblazer' database
python app.py                      # API on http://127.0.0.1:5000/api/v1.0
```

Seeded logins:

| Role | Username | Password |
|---|---|---|
| Admin | `admin` | `AdminPass123` |
| Hiker (any non-admin user) | e.g. `conor_hughes` | `Password123` |

Optional environment variables: `MONGO_URI`, `MONGO_DB`, `SECRET_KEY` (set a long random value outside development), `TOKEN_LIFETIME_MINUTES`.

## Sending data

As in the module practicals, POST/PUT/PATCH bodies can be sent from Postman as **x-www-form-urlencoded** (or form-data) fields. JSON is also accepted. With form data:

- send a location as two fields, `latitude` and `longitude`
- send a list such as `tags` as comma-separated text (`forest,views`)
- send each trail feature as its own flag (`dog_friendly=true`)

## Authentication

1. `POST /api/v1.0/auth/login` with **Basic Auth** returns a JWT.
2. Send it in the `x-access-token` header (or `Authorization: Bearer <token>`).
3. `POST /api/v1.0/auth/logout` revokes the token. Revoked tokens are kept in `blacklist` until they would have expired; a TTL index then deletes them automatically.

## Running the tests

```bash
pytest -q                          # uses a separate 'trailblazer_test' database, dropped afterwards
```

**Postman:** import `postman/TrailBlazer.postman_collection.json`, start the API, then use **Run collection**. The run creates its own user and trail and removes them at the end, so it can be repeated. From the command line:

```bash
npx newman run postman/TrailBlazer.postman_collection.json
```

## Exporting collections for submission

```bash
./scripts/export_collections.sh    # writes exports/trails.json, users.json, blacklist.json and a zip
```

On Windows, run the `mongoexport` command from the script once per collection (`trails`, `users`, `blacklist`).

## Submission checklist (from the CW1 specification)

- [ ] Zip of the code: everything except `.venv/`, `exports/` and generated files
- [ ] Zip of `mongoexport` JSON files: `./scripts/export_collections.sh`
- [ ] Video, max. 5 minutes: dataset intro, Postman demo, code walkthrough
- [ ] PDF code listing: `pip install reportlab && python scripts/make_code_listing.py`
- [ ] PDF summary of endpoints: print `docs/API_ENDPOINTS.md`
- [ ] PDF of the Postman collection run (Runner → export/print results)
- [ ] PDF of the Postman-generated API documentation (collection → View documentation → publish/print)
- [ ] Self-evaluation sheet
- [ ] Design & development document, including the AI chat history (`docs/DESIGN.md`)

See [docs/API_ENDPOINTS.md](docs/API_ENDPOINTS.md) for the full endpoint list and [docs/DESIGN.md](docs/DESIGN.md) for design decisions.
