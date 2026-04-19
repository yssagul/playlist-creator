#!/usr/bin/env python3
"""Quick test: fetch scrobbles for a specific past week."""

from datetime import datetime, timezone
from lastfm_client import LastFMClient
from week_utils import week_bounds, parse_week_key

# Change this to a week you know you were listening to music
WEEK_KEY = "26_15"   # week 15 of 2026 (Apr 6–12)

if __name__ == "__main__":
    client = LastFMClient()

    registered = client.get_user_registered_date()
    print(f"Account registered: {registered.strftime('%Y-%m-%d')}")

    year, week = parse_week_key(WEEK_KEY)
    start, end = week_bounds(year, week)
    print(f"\nFetching scrobbles for {WEEK_KEY} ({start.strftime('%b %d')} – {end.strftime('%b %d, %Y')})...")

    tracks = client.get_scrobbles_for_week(start, end)
    print(f"\nFound {len(tracks)} unique tracks:")
    for t in tracks[:20]:
        plays = f"({t['play_count']}x)" if t['play_count'] > 1 else ""
        print(f"  {t['artist']} — {t['title']} {plays}")
    if len(tracks) > 20:
        print(f"  ... and {len(tracks) - 20} more")
