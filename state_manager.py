import json
import os
from datetime import datetime, timezone


class StateManager:
    def __init__(self, path: str):
        self.path = path
        self._data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.path):
            with open(self.path) as f:
                return json.load(f)
        return {"processed_weeks": {}}

    def save(self):
        with open(self.path, "w") as f:
            json.dump(self._data, f, indent=2, default=str)

    def get_playlist_id(self, week_key: str) -> str | None:
        return self._data["processed_weeks"].get(week_key, {}).get("playlist_id")

    def set_week(self, week_key: str, playlist_id: str, track_count: int):
        self._data["processed_weeks"][week_key] = {
            "playlist_id": playlist_id,
            "track_count": track_count,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        self.save()

    def get_processed_weeks(self) -> set[str]:
        return set(self._data["processed_weeks"].keys())
