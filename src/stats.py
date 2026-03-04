import json
from pathlib import Path

STATS_PATH = Path(__file__).parent.parent / "stats.json"


def insert_all_time_clicks(current_session_clicks: int) -> None:
    if STATS_PATH.exists():
        try:
            with STATS_PATH.open("r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, ValueError):
            data = {"all_time_clicks": 0}
    else:
        data = {"all_time_clicks": 0}

    data["all_time_clicks"] += current_session_clicks

    with STATS_PATH.open("w") as f:
        json.dump(data, f)


def get_all_time_clicks() -> int:
    if STATS_PATH.exists():
        with STATS_PATH.open("r") as f:
            data = json.load(f)
        return data["all_time_clicks"]
