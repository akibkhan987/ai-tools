# TrailBlazer API – Endpoint Summary

Base URL: `http://127.0.0.1:5000/api/v1.0`

**Auth column:** — public · 🔑 any logged-in user · 👤 owner (or admin) · 🛡 admin only.
Authenticated requests send the JWT in the `x-access-token` header.
Request bodies are sent as **x-www-form-urlencoded** fields (as in the module practicals) or as JSON. In form data:

- send a location as `latitude` and `longitude`
- send lists as comma-separated text
- send trail features as individual flags, e.g. `dog_friendly=true`

Every error response has the form `{"error": "...", "details": {...}}`. An id that is malformed or doesn't exist returns **404**, following the module's API design (BE03 Table 3.2).

List endpoints return `{"this_page", "number_of_pages", "page_size", "total", "data"}`.

## Authentication

| Method | Endpoint | Auth | Description | Success | Errors |
|---|---|---|---|---|---|
| POST | `/auth/register` | — | Create an account (`username`, `email`, `password`, `name`) | 201 | 400, 409, 415 |
| POST | `/auth/login` | Basic | Log in with Basic Auth (or username/password fields); returns a JWT valid for 60 min | 200 | 401 |
| POST | `/auth/logout` | 🔑 | Revoke the current token | 200 | 401 |
| GET | `/auth/me` | 🔑 | Current user's profile | 200 | 401 |

## Trails

| Method | Endpoint | Auth | Description | Success | Errors |
|---|---|---|---|---|---|
| GET | `/trails` | — | List trails: paginated, filterable, sortable (see below) | 200 | 400 |
| GET | `/trails/nearby?lat=&lng=&radius_km=&limit=&difficulty=` | — | Trails nearest a point, with `distance_km` | 200 | 400 |
| GET | `/trails/{id}` | — | One trail with its POIs and 3 latest reviews | 200 | 404 |
| GET | `/trails/{id}/nearby?radius_km=&limit=` | — | Other trails close to this one | 200 | 400, 404 |
| POST | `/trails` | 🔑 | Create a trail | 201 | 400, 401, 409, 415 |
| PUT | `/trails/{id}` | 👤 | Replace all editable fields (all required fields needed) | 200 | 400, 401, 403, 404 |
| PATCH | `/trails/{id}` | 👤 | Update only the fields supplied | 200 | 400, 401, 403, 404 |
| DELETE | `/trails/{id}` | 👤 | Delete a trail; also removed from favourites and completed logs | 204 | 401, 403, 404 |

**`GET /trails` query parameters**

| Parameter | Example | Meaning |
|---|---|---|
| `pn`, `ps` | `pn=2&ps=10` | Page number (≥1) and page size (1–50, default 10), as in BE04 |
| `q` | `q=causeway` | Case-insensitive search of name, description and region |
| `region`, `country` | `region=Lake District` | Exact match, case-insensitive |
| `difficulty` | `difficulty=easy,moderate` | One or more of easy / moderate / hard / strenuous |
| `route_type` | `route_type=circular` | circular / linear / out-and-back |
| `min_distance`, `max_distance` | `max_distance=10` | Distance range in km |
| `min_elevation`, `max_elevation` | `max_elevation=500` | Ascent range in metres |
| `min_duration`, `max_duration` | `max_duration=180` | Duration range in minutes |
| `min_rating` | `min_rating=4.5` | Minimum average rating |
| `tags`, `tag_match` | `tags=coastal,cliffs&tag_match=all` | Match any (default) or all of the tags |
| `season` | `season=winter` | Recommended season(s) |
| `dog_friendly`, `wheelchair_accessible`, `parking`, `public_transport`, `toilets`, `cafe` | `dog_friendly=true` | Facility flags |
| `sort`, `order` | `sort=avg_rating&order=desc` | Sort by name, distance_km, elevation_gain_m, estimated_duration_mins, avg_rating, review_count or created_at |

## Reviews (sub-documents of a trail)

| Method | Endpoint | Auth | Description | Success | Errors |
|---|---|---|---|---|---|
| GET | `/trails/{id}/reviews?pn=&ps=&sort=&min_rating=` | — | Paginated reviews; sort = newest, oldest, highest, lowest or helpful | 200 | 400, 404 |
| GET | `/trails/{id}/reviews/{review_id}` | — | One review | 200 | 404 |
| POST | `/trails/{id}/reviews` | 🔑 | Add a review (`rating`, `title`, `comment`, `hiked_on`, `conditions`); one per user per trail | 201 | 400, 401, 404, 409 |
| PUT | `/trails/{id}/reviews/{review_id}` | author | Replace your review | 200 | 400, 401, 403, 404 |
| PATCH | `/trails/{id}/reviews/{review_id}` | author | Update part of your review | 200 | 400, 401, 403, 404 |
| DELETE | `/trails/{id}/reviews/{review_id}` | author or 🛡 | Delete a review | 204 | 401, 403, 404 |
| POST | `/trails/{id}/reviews/{review_id}/helpful` | 🔑 | Mark someone else's review as helpful | 201 | 401, 403, 404, 409 |
| DELETE | `/trails/{id}/reviews/{review_id}/helpful` | 🔑 | Remove your helpful vote | 204 | 401, 404 |

Adding, changing or deleting a review recalculates the trail's `avg_rating` and `review_count`.

## Points of interest (sub-documents of a trail)

| Method | Endpoint | Auth | Description | Success | Errors |
|---|---|---|---|---|---|
| GET | `/trails/{id}/pois?type=` | — | POIs ordered along the route, optionally filtered by type | 200 | 400, 404 |
| GET | `/trails/{id}/pois/{poi_id}` | — | One POI | 200 | 404 |
| POST | `/trails/{id}/pois` | 👤 | Add a POI (`name`, `type`, `location`, `description`, `km_from_start`) | 201 | 400, 401, 403, 404 |
| PUT / PATCH | `/trails/{id}/pois/{poi_id}` | 👤 | Replace or update a POI | 200 | 400, 401, 403, 404 |
| DELETE | `/trails/{id}/pois/{poi_id}` | 👤 | Delete a POI | 204 | 401, 403, 404 |

## Users

| Method | Endpoint | Auth | Description | Success | Errors |
|---|---|---|---|---|---|
| GET | `/users?q=&pn=&ps=` | 🛡 | List or search users | 200 | 401, 403 |
| GET | `/users/{user_id}` | self or 🛡 | One user | 200 | 401, 403, 404 |
| PATCH | `/users/{user_id}/role` | 🛡 | Grant or revoke admin (`{"admin": true}`) | 200 | 400, 401, 403, 404 |
| DELETE | `/users/{user_id}` | self or 🛡 | Delete an account and its reviews and votes; ratings are recalculated | 204 | 401, 403, 404 |
| GET | `/users/me` | 🔑 | Own profile | 200 | 401 |
| PATCH | `/users/me` | 🔑 | Update `name`, `email`, `password` (email or password changes need `current_password`) | 200 | 400, 401, 403, 409 |
| GET | `/users/me/favourites` | 🔑 | Favourite trails (joined with `$lookup`) | 200 | 401 |
| PUT | `/users/me/favourites/{trail_id}` | 🔑 | Add a favourite (idempotent) | 201 / 200 | 401, 404 |
| DELETE | `/users/me/favourites/{trail_id}` | 🔑 | Remove a favourite | 204 | 401, 404 |
| GET | `/users/me/completed` | 🔑 | Completed-hike log with trail details | 200 | 401 |
| POST | `/users/me/completed` | 🔑 | Log a hike (`trail_id`, `completed_on`, `duration_mins`) | 201 | 400, 401, 404 |
| DELETE | `/users/me/completed/{entry_id}` | 🔑 | Remove a log entry | 204 | 401, 404 |
| GET | `/users/me/stats` | 🔑 | Totals: hikes, distance, ascent, regions, reviews | 200 | 401 |

## Statistics (aggregation pipelines)

| Method | Endpoint | Description |
|---|---|---|
| GET | `/stats/overview` | Totals across the whole dataset |
| GET | `/stats/regions` | Trails, average distance, ascent and rating per region |
| GET | `/stats/difficulty` | Averages per difficulty level |
| GET | `/stats/distance-bands` | Histogram of trail lengths (`$bucket`) |
| GET | `/stats/tags?limit=` | Most common tags |
| GET | `/stats/top-rated?min_reviews=&limit=&region=` | Highest-rated trails with enough reviews |
| GET | `/stats/reviews/monthly` | Review count and average rating per month hiked |
| GET | `/stats/conditions` | Reported trail conditions vs. rating |

All statistics endpoints are public, use GET, and return 200 (or 400 for invalid parameters).
