import json
import os

from core.config import (
    APP_HEIGHT,
    APP_WIDTH,
    STATE_FILE,
)


DEFAULT_STATE = {
    "x": 25,
    "y": 40,
    "width": APP_WIDTH,
    "height": APP_HEIGHT,
}


def load_window_state():
    if not os.path.exists(STATE_FILE):
        return DEFAULT_STATE

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as file:
            state = json.load(file)

        return {
            "x": int(state.get("x", DEFAULT_STATE["x"])),
            "y": int(state.get("y", DEFAULT_STATE["y"])),
            "width": int(state.get("width", DEFAULT_STATE["width"])),
            "height": int(state.get("height", DEFAULT_STATE["height"])),
        }

    except Exception:
        return DEFAULT_STATE


def save_window_state(x, y, width, height):
    state = {
        "x": int(x),
        "y": int(y),
        "width": int(width),
        "height": int(height),
    }

    with open(STATE_FILE, "w", encoding="utf-8") as file:
        json.dump(state, file, indent=4)