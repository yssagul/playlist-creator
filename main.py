#!/usr/bin/env python3
"""
Last.fm → Tidal weekly playlist creator.

Fetches your Last.fm scrobbles week by week and creates Tidal playlists
named "Log YY_WW" (e.g. "Log 26_08").

Usage:
  python main.py                            # missing weeks in current year
  python main.py --scope-year 2025          # missing weeks in 2025
  python main.py --scope-week 8             # week 8 of current year
  python main.py --scope-year 2025 --scope-week 8
  python main.py --force-update             # re-process already-synced weeks
  python main.py --dry-run                  # preview without touching Tidal
"""

import argparse
import sys
from datetime import datetime, timezone

import config
from audio_features import AudioFeatures, GetSongBPM
from lastfm_client import LastFMClient
from state_manager import StateManager
from tidal_client import TidalClient
from week_utils import current_week_key, parse_week_key, week_bounds, weeks_in_year


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create Tidal playlists from Last.fm weekly listening history."
    )
    parser.add_argument(
        "--scope-year", type=int, default=None, metavar="YYYY",
        help="Limit to weeks in this year (default: current year).",
    )
    parser.add_argument(
        "--scope-week", type=int, default=None, metavar="WW",
        help="Process only this ISO week number.",
    )
    parser.add_argument(
        "--force-update", action="store_true",
        help="Re-process weeks that have already been synced.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Fetch and resolve tracks but do not create or modify playlists.",
    )
    return parser.parse_args()


# --------------------------------------------------------------------------- #
# Week selection                                                                #
# --------------------------------------------------------------------------- #

def weeks_to_process(args: argparse.Namespace, state: StateManager) -> list[str]:
    now = datetime.now(timezone.utc)
    year = args.scope_year or now.year
    this_week = current_week_key()

    if args.scope_week:
        return [f"{year % 100:02d}_{args.scope_week:02d}"]

    processed = state.get_processed_weeks()
    result = []
    for week in weeks_in_year(year):
        if week > this_week:
            break  # don't schedule future weeks
        is_current = week == this_week
        if is_current or week not in processed or args.force_update:
            result.append(week)
    return result


# --------------------------------------------------------------------------- #
# Single-week processing                                                        #
# --------------------------------------------------------------------------- #

def process_week(
    week_key: str,
    lastfm: LastFMClient,
    tidal: TidalClient,
    bpm_client: GetSongBPM | None,
    state: StateManager,
    dry_run: bool,
) -> tuple[int, int]:
    """Returns (tracks_added, tracks_failed)."""
    year, week = parse_week_key(week_key)
    start, end = week_bounds(year, week)
    playlist_name = f"Log {week_key}"
    prefix = "[DRY RUN] " if dry_run else ""

    print(f"\n{prefix}{playlist_name}  ({start.strftime('%b %d')} – {end.strftime('%b %d, %Y')})")

    # 1. Fetch scrobbles (ordered by play count desc)
    scrobbles = lastfm.get_scrobbles_for_week(start, end)
    if not scrobbles:
        print("  No scrobbles — skipping.")
        return 0, 0
    print(f"  {len(scrobbles)} unique tracks from Last.fm")

    # 2. Resolve each track on Tidal + optionally fetch BPM/key
    resolved: list[dict] = []   # {tidal_id, features}
    failures: list[dict] = []

    for i, track in enumerate(scrobbles, 1):
        artist, title = track["artist"], track["title"]
        plays = track["play_count"]
        label = f"({plays}x) " if plays > 1 else ""
        print(f"  [{i:>3}/{len(scrobbles)}] {label}{artist} — {title}", end="", flush=True)

        if dry_run:
            print("  [skipped]")
            continue

        tidal_id = tidal.search_track(artist, title)
        if not tidal_id:
            failures.append(track)
            print(" ✗ not found on Tidal")
            continue

        features = bpm_client.get(artist, title) if bpm_client else AudioFeatures.unknown()
        if features is None:
            features = AudioFeatures.unknown()

        tag = f" [{features.camelot} {features.bpm:.0f}bpm]" if features.bpm > 0 else ""
        print(f" ✓{tag}")
        resolved.append({"tidal_id": tidal_id, "features": features})

    if failures:
        _log_failures(week_key, failures)

    if dry_run:
        print(f"  [DRY RUN] Would create/update '{playlist_name}'")
        return 0, len(failures)

    if not resolved:
        print("  No tracks found on Tidal — skipping playlist creation.")
        return 0, len(failures)

    # 3. Sort by BPM (primary) then Camelot key (secondary).
    # Tracks with no BPM data inherit their predecessor's sort position
    # and are placed immediately after it (tie-breaker = 1 vs 0).
    last_sort = (0.0, 0, 0)
    for item in resolved:
        if item["features"].bpm > 0:
            last_sort = item["features"].sort_key
            item["_sort"] = last_sort + (0,)
        else:
            item["_sort"] = last_sort + (1,)

    resolved.sort(key=lambda t: t["_sort"])
    track_ids = [t["tidal_id"] for t in resolved]

    # 4. Create or update playlist
    existing_id = state.get_playlist_id(week_key)
    playlist_id = tidal.get_or_create_playlist(existing_id, playlist_name)
    tidal.clear_and_replace_tracks(playlist_id, track_ids)
    state.set_week(week_key, playlist_id, len(track_ids))

    print(f"  ✓ '{playlist_name}' — {len(track_ids)} tracks added, {len(failures)} not found")
    print(f"     https://listen.tidal.com/playlist/{playlist_id}")
    if failures:
        print(f"    Failures logged to {config.FAILURE_LOG}")

    return len(track_ids), len(failures)


def _log_failures(week_key: str, failures: list[dict]):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with open(config.FAILURE_LOG, "a") as f:
        for t in failures:
            f.write(f"{ts} | {week_key} | {t['artist']} — {t['title']}\n")


# --------------------------------------------------------------------------- #
# Entry point                                                                   #
# --------------------------------------------------------------------------- #

def main():
    args = parse_args()
    state = StateManager(config.STATE_FILE)

    print("Connecting to Last.fm...")
    lastfm = LastFMClient()

    bpm_client: GetSongBPM | None = None
    if config.GETSONGBPM_ENABLED:
        bpm_client = GetSongBPM(config.GETSONGBPM_API_KEY)
        print("BPM/key lookup: enabled (GetSongBPM)")
    else:
        print("BPM/key lookup: disabled (set GETSONGBPM_API_KEY to enable)")

    tidal = None
    if not args.dry_run:
        print("Connecting to Tidal...")
        tidal = TidalClient()

    weeks = weeks_to_process(args, state)
    if not weeks:
        print("Nothing to do. Use --force-update to re-sync existing playlists.")
        sys.exit(0)

    year = args.scope_year or datetime.now(timezone.utc).year
    if args.scope_week:
        scope = f"week {args.scope_week:02d} of {year}"
    elif args.scope_year:
        scope = f"year {args.scope_year}"
    else:
        scope = f"{year} (current year)"

    print(f"\nScope: {scope} — {len(weeks)} week(s) to process")
    if args.dry_run:
        print("Mode: DRY RUN")
    if args.force_update:
        print("Mode: FORCE UPDATE")

    total_added = total_failed = 0
    for week_key in weeks:
        added, failed = process_week(week_key, lastfm, tidal, bpm_client, state, args.dry_run)
        total_added += added
        total_failed += failed

    print(f"\n{'─' * 50}")
    print(f"Done.  {len(weeks)} playlist(s)  |  {total_added} tracks added  |  {total_failed} not found on Tidal")
    if total_failed:
        print(f"See {config.FAILURE_LOG} for details.")


if __name__ == "__main__":
    main()
