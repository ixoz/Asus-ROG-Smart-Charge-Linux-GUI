from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from asus_smart_charge.common import (
    APP_DIR,
    STATE_FILE,
    TEMP_FULL_THRESHOLD,
    VALID_THRESHOLDS,
    determine_target_threshold,
    find_battery_threshold_path,
    load_state,
    read_battery_status,
    save_state,
    utc_now_iso,
)


def _require_root() -> None:
    if os.geteuid() != 0:
        raise PermissionError("This action requires root privileges. Run it through pkexec or sudo.")


def _write_threshold(value: int) -> None:
    if value not in VALID_THRESHOLDS:
        raise ValueError(f"Unsupported threshold: {value}")
    threshold_path = find_battery_threshold_path()
    threshold_path.write_text(f"{value}\n", encoding="utf-8")


def command_status(_args: argparse.Namespace) -> int:
    state = load_state()
    battery = read_battery_status()
    effective_state = state.copy()
    target, reverted = determine_target_threshold(effective_state, battery.capacity)
    payload = {
        "config_path": str(STATE_FILE),
        "battery_name": battery.battery_name,
        "battery_percent": battery.capacity,
        "charging_status": battery.charging_status,
        "applied_threshold": battery.applied_threshold,
        "selected_threshold": state["selected_threshold"],
        "temporary_full": state["temporary_full"],
        "temporary_full_started_at": state.get("temporary_full_started_at"),
        "effective_target": target,
        "reverted_to_default": reverted,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def command_set_default(args: argparse.Namespace) -> int:
    _require_root()
    threshold = int(args.threshold)
    if threshold not in VALID_THRESHOLDS:
        raise ValueError(f"Threshold must be one of {VALID_THRESHOLDS}")

    state = load_state()
    state["selected_threshold"] = threshold
    state["temporary_full"] = False
    state["temporary_full_started_at"] = None
    _write_threshold(threshold)
    state["last_applied_threshold"] = threshold
    save_state(state)
    return command_status(args)


def command_charge_once(_args: argparse.Namespace) -> int:
    _require_root()
    state = load_state()
    state["temporary_full"] = True
    state["temporary_full_started_at"] = utc_now_iso()
    _write_threshold(TEMP_FULL_THRESHOLD)
    state["last_applied_threshold"] = TEMP_FULL_THRESHOLD
    save_state(state)
    return command_status(argparse.Namespace())


def command_enforce(_args: argparse.Namespace) -> int:
    _require_root()
    state = load_state()
    battery = read_battery_status()
    target, reverted = determine_target_threshold(state, battery.capacity)
    _write_threshold(target)
    state["last_applied_threshold"] = target
    save_state(state)

    payload = {
        "battery_percent": battery.capacity,
        "charging_status": battery.charging_status,
        "selected_threshold": state["selected_threshold"],
        "temporary_full": state["temporary_full"],
        "effective_target": target,
        "reverted_to_default": reverted,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def command_bootstrap(_args: argparse.Namespace) -> int:
    _require_root()
    APP_DIR.mkdir(parents=True, exist_ok=True)
    if not STATE_FILE.exists():
        save_state(load_state())
    if not Path(STATE_FILE).exists():
        raise RuntimeError("Failed to initialize state file.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Asus Smart Charge privileged helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser("status", help="Show current battery threshold state")
    status.set_defaults(func=command_status)

    set_default = subparsers.add_parser("set-default", help="Set the default threshold")
    set_default.add_argument("threshold", type=int)
    set_default.set_defaults(func=command_set_default)

    charge_once = subparsers.add_parser("charge-once", help="Temporarily charge to 100 percent")
    charge_once.set_defaults(func=command_charge_once)

    enforce = subparsers.add_parser("enforce", help="Apply the configured threshold")
    enforce.set_defaults(func=command_enforce)

    bootstrap = subparsers.add_parser("bootstrap", help="Create the initial state directory and file")
    bootstrap.set_defaults(func=command_bootstrap)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - small CLI surface
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
