from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


APP_DIR = Path("/etc/asus-smart-charge")
STATE_FILE = APP_DIR / "state.json"
SYSFS_GLOB = "/sys/class/power_supply/BAT*/charge_control_end_threshold"
VALID_THRESHOLDS = (55, 60, 70, 80, 100)
TEMP_FULL_THRESHOLD = 100
TEMP_FULL_RESET_AT = 99


@dataclass
class BatteryStatus:
    battery_name: str
    threshold_path: Path
    capacity: int | None
    charging_status: str
    applied_threshold: int | None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_state() -> dict:
    return {
        "selected_threshold": 80,
        "temporary_full": False,
        "temporary_full_started_at": None,
        "last_applied_threshold": None,
        "last_updated_at": None,
    }


def load_state() -> dict:
    state = default_state()
    if STATE_FILE.exists():
        with STATE_FILE.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict):
            state.update(loaded)

    selected = int(state.get("selected_threshold", 80))
    if selected not in VALID_THRESHOLDS:
        raise ValueError(f"Unsupported threshold in state: {selected}")
    state["selected_threshold"] = selected
    state["temporary_full"] = bool(state.get("temporary_full", False))
    return state


def save_state(state: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    state["last_updated_at"] = utc_now_iso()
    temp_file = STATE_FILE.with_suffix(".tmp")
    with temp_file.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
        handle.write("\n")
    temp_file.replace(STATE_FILE)


def find_battery_threshold_path() -> Path:
    candidates = sorted(Path("/sys/class/power_supply").glob("BAT*/charge_control_end_threshold"))
    if not candidates:
        raise FileNotFoundError("No supported battery threshold file was found in /sys/class/power_supply.")

    preferred = [path for path in candidates if path.parts[-2] == "BAT1"]
    return preferred[0] if preferred else candidates[0]


def _read_int(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError, OSError):
        return None


def read_battery_status() -> BatteryStatus:
    threshold_path = find_battery_threshold_path()
    battery_dir = threshold_path.parent
    battery_name = battery_dir.name
    return BatteryStatus(
        battery_name=battery_name,
        threshold_path=threshold_path,
        capacity=_read_int(battery_dir / "capacity"),
        charging_status=(battery_dir / "status").read_text(encoding="utf-8").strip(),
        applied_threshold=_read_int(threshold_path),
    )


def determine_target_threshold(state: dict, capacity: int | None) -> tuple[int, bool]:
    selected = int(state["selected_threshold"])
    if state.get("temporary_full"):
        if capacity is not None and capacity >= TEMP_FULL_RESET_AT:
            state["temporary_full"] = False
            state["temporary_full_started_at"] = None
            return selected, True
        return TEMP_FULL_THRESHOLD, False
    return selected, False
