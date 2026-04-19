"""
Tidal API client using the official REST API (openapi.tidal.com/v2).
All operations use the authenticated session from tidal_auth.TidalAuth.
"""

import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Optional

import certifi

from tidal_auth import TidalAuth

API_BASE = "https://openapi.tidal.com/v2"
COUNTRY_CODE = "US"
_SSL = ssl.create_default_context(cafile=certifi.where())


def _request(
    method: str,
    path: str,
    auth: TidalAuth,
    params: dict = None,
    body: dict = None,
    idempotency_key: str = None,
) -> Optional[dict]:
    url = f"{API_BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)

    headers = auth.headers()
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key

    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, context=_SSL) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            print(f"  [Tidal] HTTP {e.code} on {method} {path}: {error_body[:300]}")
            return None
        except OSError as e:
            if attempt < 2:
                delay = 2 ** attempt
                print(f"  [Tidal] Connection error ({e}), retrying in {delay}s...")
                time.sleep(delay)
            else:
                print(f"  [Tidal] Connection error after 3 attempts: {e}")
                return None


def _get(auth, path, params=None):
    return _request("GET", path, auth, params=params)


def _post(auth, path, body, params=None):
    return _request(
        "POST", path, auth,
        params=params,
        body=body,
        idempotency_key=str(uuid.uuid4()),
    )


def _delete(auth, path, body, params=None):
    return _request("DELETE", path, auth, params=params, body=body)


def _clean_title(title: str) -> str:
    """Strip featuring artists and remix/edit suffixes to improve search accuracy."""
    # Remove (feat. X), (ft. X), (with X), [feat. X], (featuring X)
    title = re.sub(
        r'[\(\[]\s*(?:feat\.?|ft\.?|with|featuring)\s+[^\)\]]+[\)\]]',
        '', title, flags=re.IGNORECASE,
    )
    # Remove trailing "- X Remix", "- X Edit", "- X Mix", "- X Rework", "- X Version"
    title = re.sub(
        r'\s*-\s+[^-]+(?:remix|edit|mix|rework|version|dub)\s*$',
        '', title, flags=re.IGNORECASE,
    )
    # Remove trailing "(X Remix)", "(X Edit)" etc. in parentheses
    title = re.sub(
        r'\s*[\(\[][^\)\]]*(?:remix|edit|mix|rework|version|dub)[^\)\]]*[\)\]]\s*$',
        '', title, flags=re.IGNORECASE,
    )
    return title.strip()


class TidalClient:
    def __init__(self):
        self.auth = TidalAuth()

    # ------------------------------------------------------------------ #
    # Search                                                               #
    # ------------------------------------------------------------------ #

    def search_track(self, artist: str, title: str) -> Optional[str]:
        """
        Search for a track using progressive fallback strategies.
        Returns the Tidal track ID of the best match, or None if not found.
        """
        first_artist = artist.split(",")[0].strip()
        clean = _clean_title(title)

        # Build query list, deduplicated, in priority order
        seen: set[str] = set()
        queries: list[str] = []
        for q in [
            f"{first_artist} {clean}",   # most targeted
            f"{first_artist} {title}",
            f"{artist} {clean}",
            f"{artist} {title}",
            clean,                        # title only as last resort
        ]:
            q = q.strip()
            if q and q not in seen:
                seen.add(q)
                queries.append(q)

        for query in queries:
            result = self._search_query(query)
            if result:
                return result

        return None

    def _search_query(self, query: str) -> Optional[str]:
        """Execute a single search query; return first track ID from topHits or tracks."""
        encoded = urllib.parse.quote(query)
        params = {"countryCode": COUNTRY_CODE, "include": "topHits,tracks"}

        resp = _get(self.auth, f"/searchResults/{encoded}", params)
        if not resp:
            # One retry after a brief pause in case of transient rate limiting
            time.sleep(1.0)
            resp = _get(self.auth, f"/searchResults/{encoded}", params)
        if not resp:
            return None

        relationships = resp.get("data", {}).get("relationships", {})

        # topHits: Tidal's ranked relevance — filter to tracks only
        for hit in relationships.get("topHits", {}).get("data", []):
            if hit.get("type") == "tracks":
                time.sleep(0.3)
                return str(hit["id"])

        # Fall back to raw tracks list
        tracks = relationships.get("tracks", {}).get("data", [])
        if tracks:
            time.sleep(0.3)
            return str(tracks[0]["id"])

        time.sleep(0.3)
        return None

    # ------------------------------------------------------------------ #
    # Playlists                                                            #
    # ------------------------------------------------------------------ #

    def get_or_create_playlist(self, existing_id: Optional[str], name: str) -> str:
        """Return existing playlist ID if valid, otherwise create a new one."""
        if existing_id:
            # Verify it still exists
            resp = _get(self.auth, f"/playlists/{existing_id}", {"countryCode": COUNTRY_CODE})
            if resp and resp.get("data"):
                return existing_id
            print(f"  [Tidal] Playlist {existing_id} not found — creating new one.")

        new_id = self.create_playlist(name, f"Weekly listening log — {name}")
        if not new_id:
            raise RuntimeError(f"Failed to create Tidal playlist '{name}'")
        return new_id

    def create_playlist(self, name: str, description: str = "") -> Optional[str]:
        """Create a new private playlist. Returns its UUID string ID."""
        resp = _post(
            self.auth,
            "/playlists",
            body={
                "data": {
                    "type": "playlists",
                    "attributes": {
                        "name": name,
                        "description": description,
                        "privacy": "PRIVATE",
                    },
                }
            },
            params={"countryCode": COUNTRY_CODE},
        )
        if not resp:
            return None
        return resp.get("data", {}).get("id")

    def get_playlist_track_ids(self, playlist_id: str) -> list[str]:
        """Return the ordered list of track IDs currently in a playlist."""
        ids = []
        params = {"countryCode": COUNTRY_CODE}
        path = f"/playlists/{playlist_id}/relationships/items"

        while path:
            resp = _get(self.auth, path, params=params)
            if not resp:
                break
            for item in resp.get("data", []):
                if item.get("type") == "tracks":
                    ids.append(str(item["id"]))
            # Follow pagination
            next_link = resp.get("links", {}).get("next")
            if next_link:
                # next_link is a relative path, may include query params
                parsed = urllib.parse.urlparse(next_link)
                path = parsed.path
                params = dict(urllib.parse.parse_qsl(parsed.query))
            else:
                path = None

        return ids

    def add_tracks(self, playlist_id: str, track_ids: list[str]):
        """Add tracks to a playlist in batches of 20."""
        for i in range(0, len(track_ids), 20):
            batch = track_ids[i : i + 20]
            _post(
                self.auth,
                f"/playlists/{playlist_id}/relationships/items",
                body={"data": [{"type": "tracks", "id": tid} for tid in batch]},
                params={"countryCode": COUNTRY_CODE},
            )
            time.sleep(0.3)

    def clear_tracks(self, playlist_id: str) -> bool:
        """
        Remove all tracks from a playlist. Returns True on success.
        Falls back gracefully if the DELETE endpoint is unavailable.
        """
        existing = self.get_playlist_track_ids(playlist_id)
        if not existing:
            return True

        # JSON:API relationship deletion
        resp = _delete(
            self.auth,
            f"/playlists/{playlist_id}/relationships/items",
            body={"data": [{"type": "tracks", "id": tid} for tid in existing]},
            params={"countryCode": COUNTRY_CODE},
        )
        return resp is not None

    def clear_and_replace_tracks(self, playlist_id: str, track_ids: list[str]):
        """
        Replace a playlist's contents with track_ids in order.
        Clears first, then adds in sorted batches.
        """
        cleared = self.clear_tracks(playlist_id)
        if not cleared:
            print("  [Tidal] Warning: could not clear existing tracks — appending instead.")
        self.add_tracks(playlist_id, track_ids)
