#!/usr/bin/env python3
"""Quick test: fetch BPM + key for a handful of tracks via GetSongBPM."""

from audio_features import GetSongBPM
from config import GETSONGBPM_API_KEY, GETSONGBPM_ENABLED

TEST_TRACKS = [
    ("Above & Beyond", "Sun & Moon"),
    ("Disclosure", "Latch"),
    ("Fred again..", "Ambery"),
    ("Skrillex", "Scary Monsters and Nice Sprites"),
    ("Daft Punk", "Get Lucky"),
    ("Above & Beyond", "Black Room Boy"),
    ("Gorgon City", "Ready For Your Love"),
]

if __name__ == "__main__":
    if not GETSONGBPM_ENABLED:
        print("GETSONGBPM_API_KEY not set in .env")
        raise SystemExit(1)

    client = GetSongBPM(GETSONGBPM_API_KEY)

    for artist, title in TEST_TRACKS:
        features = client.get(artist, title)
        if features and features.bpm > 0:
            print(f"✓ {artist} — {title}: {features.bpm:.0f} BPM, {features.camelot} ({features.key_label})")
        else:
            print(f"✗ {artist} — {title}: not found")
