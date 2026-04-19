"""
BPM and key lookup via GetSongBPM (api.getsong.co).
Open Key notation from the API maps to Camelot with a fixed offset:
  camelot_number = ((open_key_number + 7) % 12) or 12
  'm' -> 'A' (minor), 'd' -> 'B' (major)
"""

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional

import certifi

_SSL = ssl.create_default_context(cafile=certifi.where())
API_BASE = "https://api.getsong.co"


def _open_key_to_camelot(open_key: str) -> tuple[int, str]:
    """Convert Open Key string (e.g. '4m', '1d') to (camelot_number, letter)."""
    num = int(open_key[:-1])
    letter = "A" if open_key[-1] == "m" else "B"
    camelot_num = ((num + 7) % 12) or 12
    return camelot_num, letter


@dataclass
class AudioFeatures:
    bpm: float
    camelot: str        # e.g. "11A", "8B"
    key_label: str      # e.g. "F♯m", "C major" — for display only
    sort_key: tuple     # (bpm, camelot_number, letter_rank) for sorting

    @classmethod
    def from_api(cls, song: dict) -> "AudioFeatures":
        bpm = float(song.get("tempo", 0) or 0)
        open_key = song.get("open_key", "")
        key_label = song.get("key_of", "?")

        if open_key:
            camelot_num, letter = _open_key_to_camelot(open_key)
            camelot = f"{camelot_num}{letter}"
            letter_rank = 0 if letter == "A" else 1
        else:
            camelot = "?"
            camelot_num, letter_rank = 0, 0

        return cls(
            bpm=bpm,
            camelot=camelot,
            key_label=key_label,
            sort_key=(bpm, camelot_num, letter_rank),
        )

    @classmethod
    def unknown(cls) -> "AudioFeatures":
        return cls(bpm=0.0, camelot="?", key_label="?", sort_key=(float("inf"), 0, 0))


class GetSongBPM:
    def __init__(self, api_key: str):
        self._api_key = api_key

    def get(self, artist: str, title: str) -> Optional[AudioFeatures]:
        """Look up BPM and key for a track. Returns None if not found."""
        first_artist = artist.split(",")[0].strip()
        # Use urlencode so all special characters (dots, quotes, etc.) are handled correctly
        lookup = f"song:{title} artist:{first_artist}"
        query = urllib.parse.urlencode({
            "api_key": self._api_key,
            "type": "both",
            "lookup": lookup,
            "limit": "1",
        })
        url = f"{API_BASE}/search/?{query}"

        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, context=_SSL) as resp:
                data = json.loads(resp.read())
            results = data.get("search", [])
            # API returns a dict like {'error': 'no result'} when not found
            if not isinstance(results, list) or not results:
                return None
            return AudioFeatures.from_api(results[0])
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(f"\n  [GetSongBPM] HTTP {e.code} for '{artist} — {title}': {body[:200]}")
            return None
        except Exception as e:
            print(f"\n  [GetSongBPM] {type(e).__name__} for '{artist} — {title}': {e}")
            return None
        finally:
            time.sleep(0.5)  # stay within 3000 req/hour limit
