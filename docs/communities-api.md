# Communities API

All paths below are under your API base (for example `http://localhost:8000/api`). Every endpoint requires an authenticated user: send `Authorization: Bearer <access_token>` from login/register, or use the session cookie flow if your app already does that for other `/api` routes.

Common JSON shapes:

- **Community** — `id` (UUID), `name`, `description`, `website` (optional URL string or `null`), `created_by_user_id` (UUID or `null` if the creator account was removed), `created_at` (ISO 8601).
- **Community event** — `id`, `community_id`, `name`, `event_at` (ISO 8601 datetime with timezone), `location`, `description`, `website` (optional URL string or `null`), `created_at`.

---

## Communities

### `GET /communities`

List communities, newest first.

### `POST /communities`

Create a community. The current user becomes the owner (`created_by_user_id`).

**Body**

```json
{
  "name": "GDG On Campus",
  "description": "Google Developer student community.",
  "website": "https://example.com/gdg"
}
```

`description` may be an empty string. `website` is optional; omit it or set it to `null`. Empty strings are stored as `null`.

### `GET /communities/{community_id}`

Get one community by UUID.

### `PATCH /communities/{community_id}`

Update any of `name`, `description`, or `website`. Only the community creator or a `superadmin` may call this.

**Body** (at least one field)

```json
{
  "name": "GDG",
  "description": "Updated description.",
  "website": null
}
```

Send `"website": null` (or `""`) to clear a previously set website.

### `DELETE /communities/{community_id}`

Delete the community and its events, subscriptions, and favorites (via database cascades). Same permission rules as `PATCH`.

---

## Community events

Events belong to a single community. Paths nest under that community.

### `GET /communities/{community_id}/events`

List events for the community, ordered by `event_at` ascending.

### `POST /communities/{community_id}/events`

Create an event. Only the community creator or `superadmin`.

**Body**

```json
{
  "name": "Intro to APIs",
  "event_at": "2026-05-01T17:00:00+03:00",
  "location": "Engineering Building, Room 204",
  "description": "Hands-on workshop.",
  "website": "https://example.com/rsvp"
}
```

`website` is optional on create, same rules as for communities.

### `GET /communities/{community_id}/events/{event_id}`

Get one event. `event_id` must belong to `community_id`.

### `PATCH /communities/{community_id}/events/{event_id}`

Partial update; include any of `name`, `event_at`, `location`, `description`, `website`. Same permissions as create.

### `DELETE /communities/{community_id}/events/{event_id}`

Delete the event. Same permissions as create.

---

## Subscribe to a community

### `POST /communities/{community_id}/subscribe`

Subscribe the current user. Idempotent: if already subscribed, returns `200` with `subscribed: true`.

**Response**

```json
{
  "community_id": "…uuid…",
  "subscribed": true
}
```

### `DELETE /communities/{community_id}/subscribe`

Unsubscribe. Returns `404` if the user was not subscribed.

**Response**

```json
{
  "community_id": "…uuid…",
  "subscribed": false
}
```

### `GET /communities/me/subscriptions`

List communities the current user is subscribed to (same shape as `GET /communities` items).

---

## Favorite an event

### `POST /communities/{community_id}/events/{event_id}/favorite`

Add the event to the user’s favorites (interests). Idempotent if already favorited.

**Response**

```json
{
  "event_id": "…uuid…",
  "favorited": true
}
```

### `DELETE /communities/{community_id}/events/{event_id}/favorite`

Remove from favorites. Returns `404` if it was not favorited.

### `GET /communities/me/favorite-events`

List favorited events for the current user (full event objects, including `community_id`).

---

## Errors

| Status | Meaning |
|--------|---------|
| `401` | Missing or invalid auth |
| `403` | Authenticated but not allowed to modify this community or its events |
| `404` | Community, event, subscription, or favorite not found (where applicable) |
| `400` | Empty `PATCH` body (no fields to update) |

Interactive schemas and “Try it” forms are also available in the FastAPI OpenAPI UI (`/docs`) under the **communities** tag.
