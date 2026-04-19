# playlist-creator

Pulls your Last.fm scrobble history week by week and creates Tidal playlists named `Log YY_WW` (e.g. `Log 26_15`). Tracks are sorted by BPM and Camelot key via GetSongBPM, so each playlist flows well for DJing.

## How it works

1. Fetches scrobbles from Last.fm for a given ISO week, deduplicated by track
2. Searches each track on Tidal using progressive fallback queries
3. Looks up BPM and key via GetSongBPM (optional)
4. Sorts tracks by BPM → Camelot key; tracks with no BPM data are placed after their predecessor in the play-count order
5. Creates or updates a Tidal playlist for that week

Processed weeks are tracked in `.playlist_state.json` so re-runs are idempotent. The current week is always re-processed to pick up new scrobbles. Tracks not found on Tidal are logged to `transfer_failures.log`.

## Setup

**Requirements:** Python 3.11+

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|---|---|---|
| `LASTFM_API_KEY` | Yes | Last.fm API key |
| `LASTFM_API_SECRET` | Yes | Last.fm API secret |
| `LASTFM_USERNAME` | Yes | Your Last.fm username |
| `TIDAL_CLIENT_ID` | Yes | Tidal app client ID |
| `TIDAL_CLIENT_SECRET` | Yes | Tidal app client secret |
| `GETSONGBPM_API_KEY` | No | Enables BPM/key sorting |

On first run, Tidal will open a browser tab for OAuth login. The session is saved to `.tidal_session.json` and refreshed automatically.

## Usage

```bash
# Process all missing weeks in the current year
python main.py

# Process a specific week (current year)
python main.py --scope-week 15

# Process a specific week in a specific year
python main.py --scope-year 2025 --scope-week 52

# Process all missing weeks in a given year
python main.py --scope-year 2025

# Re-process weeks that have already been synced
python main.py --force-update

# Preview without creating or modifying any playlists
python main.py --dry-run
```

## APIs used

- [Last.fm API](https://www.last.fm/api) — scrobble history
- [Tidal API](https://developer.tidal.com) — playlist creation (official REST API)
- [GetSongBPM](https://getsongbpm.com/api) — BPM and key data

Attribution: Song BPM and key provided by [GetSongBPM](https://getsongbpm.com/api).
