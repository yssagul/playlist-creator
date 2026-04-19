"""
Tidal OAuth 2.1 Authorization Code + PKCE flow.

On first run: opens a browser tab for the user to log in to Tidal.
The local server on port 8888 catches the redirect and exchanges the
code for tokens. Tokens are saved to disk and refreshed automatically.
"""

import base64
import hashlib
import http.server
import json
import os
import secrets
import ssl
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Optional

import certifi

_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

from config import TIDAL_CLIENT_ID, TIDAL_CLIENT_SECRET, TIDAL_SESSION_FILE

AUTH_ENDPOINT = "https://login.tidal.com/authorize"
TOKEN_ENDPOINT = "https://auth.tidal.com/v1/oauth2/token"
REDIRECT_URI = "http://localhost:8888/callback"
SCOPES = "user.read collection.read collection.write search.read playlists.read playlists.write entitlements.read recommendations.read"


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------

def _pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge)."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


# ---------------------------------------------------------------------------
# Local callback server
# ---------------------------------------------------------------------------

class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    code: Optional[str] = None
    error: Optional[str] = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            _CallbackHandler.code = params["code"][0]
            body = b"<h2>Authentication successful. You can close this tab.</h2>"
        elif "error" in params:
            _CallbackHandler.error = params.get("error_description", params["error"])[0]
            body = b"<h2>Authentication failed. Check the terminal.</h2>"
        else:
            body = b"<h2>Unexpected callback.</h2>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # suppress access log


def _wait_for_code(timeout: int = 120) -> str:
    """Start local server, block until code arrives, return it."""
    server = http.server.HTTPServer(("localhost", 8888), _CallbackHandler)
    server.timeout = 1
    deadline = time.time() + timeout
    while time.time() < deadline:
        server.handle_request()
        if _CallbackHandler.code:
            server.server_close()
            return _CallbackHandler.code
        if _CallbackHandler.error:
            server.server_close()
            raise RuntimeError(f"Tidal auth error: {_CallbackHandler.error}")
    server.server_close()
    raise TimeoutError("Timed out waiting for Tidal login callback.")


# ---------------------------------------------------------------------------
# Token exchange / refresh
# ---------------------------------------------------------------------------

def _post_token(params: dict) -> dict:
    credentials = base64.b64encode(
        f"{TIDAL_CLIENT_ID}:{TIDAL_CLIENT_SECRET}".encode()
    ).decode()
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(
        TOKEN_ENDPOINT,
        data=data,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, context=_SSL_CONTEXT) as resp:
        return json.loads(resp.read())


def _exchange_code(code: str, verifier: str) -> dict:
    return _post_token({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": verifier,
        "client_id": TIDAL_CLIENT_ID,
    })


def _refresh(refresh_token: str) -> dict:
    return _post_token({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": TIDAL_CLIENT_ID,
    })


# ---------------------------------------------------------------------------
# Session persistence
# ---------------------------------------------------------------------------

def _save(tokens: dict):
    with open(TIDAL_SESSION_FILE, "w") as f:
        json.dump(tokens, f, indent=2)


def _load() -> Optional[dict]:
    if not os.path.exists(TIDAL_SESSION_FILE):
        return None
    with open(TIDAL_SESSION_FILE) as f:
        return json.load(f)


def _is_expired(tokens: dict) -> bool:
    exp = tokens.get("expires_at")
    if not exp:
        return True
    return datetime.fromisoformat(exp) <= datetime.now(timezone.utc) + timedelta(seconds=60)


def _attach_expiry(tokens: dict) -> dict:
    expires_in = tokens.get("expires_in", 3600)
    tokens["expires_at"] = (
        datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    ).isoformat()
    return tokens


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

class TidalAuth:
    """
    Holds a valid Tidal access token and refreshes it automatically.

    Usage:
        auth = TidalAuth()
        headers = auth.headers()   # pass to every API request
    """

    def __init__(self):
        self._tokens = self._get_valid_tokens()

    def _get_valid_tokens(self) -> dict:
        stored = _load()

        if stored and not _is_expired(stored):
            return stored

        if stored and stored.get("refresh_token"):
            try:
                print("[Tidal] Access token expired — refreshing...")
                fresh = _attach_expiry(_refresh(stored["refresh_token"]))
                # Preserve refresh_token if not returned in response
                if "refresh_token" not in fresh:
                    fresh["refresh_token"] = stored["refresh_token"]
                _save(fresh)
                return fresh
            except Exception as e:
                print(f"[Tidal] Refresh failed ({e}), re-authenticating...")

        return self._full_login()

    def _full_login(self) -> dict:
        verifier, challenge = _pkce_pair()
        params = urllib.parse.urlencode({
            "response_type": "code",
            "client_id": TIDAL_CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPES,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        })
        url = f"{AUTH_ENDPOINT}?{params}"

        print("\n[Tidal] Opening browser for login...")
        print(f"If the browser doesn't open, visit:\n  {url}\n")
        import webbrowser
        webbrowser.open(url)

        print("[Tidal] Waiting for login callback on http://localhost:8888 ...")
        code = _wait_for_code()
        tokens = _attach_expiry(_exchange_code(code, verifier))
        _save(tokens)
        print("[Tidal] Authenticated successfully.\n")
        return tokens

    def headers(self) -> dict:
        """Return Authorization headers for an API request, refreshing if needed."""
        if _is_expired(self._tokens):
            self._tokens = self._get_valid_tokens()
        return {
            "Authorization": f"Bearer {self._tokens['access_token']}",
            "Content-Type": "application/vnd.api+json",
        }

    @property
    def user_id(self) -> Optional[str]:
        return self._tokens.get("user", {}).get("userId") or self._tokens.get("userId")
