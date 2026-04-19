import ssl

import certifi
import pylast
from datetime import datetime, timezone

# pylast builds its SSL context at import time using the system store, which
# fails on macOS without the cert installer. Patch it to use certifi instead.
pylast.SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

from config import LASTFM_API_KEY, LASTFM_API_SECRET, LASTFM_USERNAME


class LastFMClient:
    def __init__(self):
        self.network = pylast.LastFMNetwork(
            api_key=LASTFM_API_KEY,
            api_secret=LASTFM_API_SECRET,
        )
        self.user = self.network.get_user(LASTFM_USERNAME)

    def get_scrobbles_for_week(
        self, week_start: datetime, week_end: datetime, chronological: bool = False
    ) -> list[dict]:
        """
        Return tracks scrobbled in [week_start, week_end], deduplicated by
        (artist, title). Each entry: {artist, title, play_count}.

        chronological=False (default): sorted by play_count descending.
        chronological=True: sorted by first play, oldest first.
        """
        start_ts = int(week_start.timestamp())
        end_ts = int(week_end.timestamp())

        play_counts: dict[tuple[str, str], int] = {}
        canonical: dict[tuple[str, str], dict] = {}
        order: list[tuple[str, str]] = []  # insertion order for chronological mode

        try:
            items = self.user.get_recent_tracks(
                limit=None,
                time_from=start_ts,
                time_to=end_ts,
                stream=True,
            )
            raw = [item for item in items if item.timestamp]
            # API returns newest-first; reverse for oldest-first chronological order
            if chronological:
                raw = list(reversed(raw))
            for item in raw:
                artist = item.track.artist.name
                title = item.track.title
                key = (artist.lower(), title.lower())
                play_counts[key] = play_counts.get(key, 0) + 1
                if key not in canonical:
                    canonical[key] = {"artist": artist, "title": title}
                    order.append(key)
        except pylast.WSError as e:
            print(f"  [Last.fm] API error: {e}")

        if chronological:
            return [{**canonical[k], "play_count": play_counts[k]} for k in order]
        return [
            {**canonical[k], "play_count": play_counts[k]}
            for k in sorted(play_counts, key=lambda k: -play_counts[k])
        ]

    def get_user_registered_date(self) -> datetime:
        ts = int(self.user.get_registered())
        return datetime.fromtimestamp(ts, tz=timezone.utc)
