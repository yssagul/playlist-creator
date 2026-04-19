import os
from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise ValueError(f"Missing required environment variable: {name}")
    return val


LASTFM_API_KEY = _require("LASTFM_API_KEY")
LASTFM_API_SECRET = _require("LASTFM_API_SECRET")
LASTFM_USERNAME = _require("LASTFM_USERNAME")

TIDAL_CLIENT_ID = _require("TIDAL_CLIENT_ID")
TIDAL_CLIENT_SECRET = _require("TIDAL_CLIENT_SECRET")

GETSONGBPM_API_KEY = os.environ.get("GETSONGBPM_API_KEY", "").strip()
GETSONGBPM_ENABLED = bool(GETSONGBPM_API_KEY)

STATE_FILE = os.environ.get("STATE_FILE", ".playlist_state.json").strip()
TIDAL_SESSION_FILE = os.environ.get("TIDAL_SESSION_FILE", ".tidal_session.json").strip()
FAILURE_LOG = os.environ.get("FAILURE_LOG", "transfer_failures.log").strip()
