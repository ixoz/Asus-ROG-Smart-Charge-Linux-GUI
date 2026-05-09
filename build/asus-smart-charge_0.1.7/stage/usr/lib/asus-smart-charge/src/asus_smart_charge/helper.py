from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from asus_smart_charge.common import (
    APP_DIR,
    ASUS_THERMAL_POLICY_MAP,
    ASUS_THERMAL_POLICY_PATH,
    KBD_BACKLIGHT_PATH,
    KEYBOARD_LIGHTING_MODE_MAP,
    KEYBOARD_LIGHTING_SPEED_MAP,
    PLATFORM_PROFILE_MAP,
    PLATFORM_PROFILE_PATH,
    STATE_FILE,
    TEMP_FULL_THRESHOLD,
    VALID_THRESHOLDS,
    determine_target_threshold,
    find_cpufreq_dirs,
    find_battery_threshold_path,
    load_state,
    read_battery_status,
    read_cpu_clock_status,
    read_keyboard_lighting_status,
    read_thermal_profile_status,
    save_state,
    utc_now_iso,
    validate_cpu_max_freq,
    validate_hex_color,
    validate_keyboard_brightness,
    validate_keyboard_mode,
    validate_keyboard_speed,
    validate_thermal_profile,
)


def _require_root() -> None:
    if os.geteuid() != 0:
        raise PermissionError("This action requires root privileges. Run it through pkexec or sudo.")


def _write_threshold(value: int) -> None:
    if value not in VALID_THRESHOLDS:
        raise ValueError(f"Unsupported threshold: {value}")
    threshold_path = find_battery_threshold_path()
    threshold_path.write_text(f"{value}\n", encoding="utf-8")


def _write_cpu_max_freq(freq_khz: int) -> None:
    status = read_cpu_clock_status()
    validate_cpu_max_freq(freq_khz, status)
    cpufreq_dirs = find_cpufreq_dirs()
    if not cpufreq_dirs:
        raise FileNotFoundError("No CPU frequency control files were found.")
    for cpufreq_dir in cpufreq_dirs:
        (cpufreq_dir / "scaling_max_freq").write_text(f"{freq_khz}\n", encoding="utf-8")


def _cpu_clock_payload() -> dict:
    status = read_cpu_clock_status()
    return {
        "supported": status.supported,
        "cpu_count": status.cpu_count,
        "min_freq_khz": status.min_freq_khz,
        "max_freq_khz": status.max_freq_khz,
        "current_max_freq_khz": status.current_max_freq_khz,
        "current_freq_khz": status.current_freq_khz,
        "governor": status.governor,
        "temperature_c": status.temperature_c,
    }


def _write_thermal_profile(profile: str) -> None:
    validate_thermal_profile(profile)
    wrote = False
    if PLATFORM_PROFILE_PATH.exists():
        PLATFORM_PROFILE_PATH.write_text(f"{PLATFORM_PROFILE_MAP[profile]}\n", encoding="utf-8")
        wrote = True
    if ASUS_THERMAL_POLICY_PATH.exists():
        ASUS_THERMAL_POLICY_PATH.write_text(f"{ASUS_THERMAL_POLICY_MAP[profile]}\n", encoding="utf-8")
        wrote = True
    if not wrote:
        raise FileNotFoundError("Thermal profile control is not supported on this system.")


def _thermal_profile_payload() -> dict:
    status = read_thermal_profile_status()
    return {
        "supported": status.supported,
        "active_profile": status.active_profile,
        "available_profiles": status.available_profiles,
        "backend": status.backend,
    }


def _write_keyboard_lighting(brightness: int, mode: str, color: str, speed: str) -> None:
    max_brightness = read_keyboard_lighting_status().max_brightness
    validate_keyboard_brightness(brightness, max_brightness)
    validate_keyboard_mode(mode)
    validate_hex_color(color)
    validate_keyboard_speed(speed)

    brightness_path = KBD_BACKLIGHT_PATH / "brightness"
    rgb_state_path = KBD_BACKLIGHT_PATH / "kbd_rgb_state"
    rgb_mode_path = KBD_BACKLIGHT_PATH / "kbd_rgb_mode"
    if not brightness_path.exists():
        raise FileNotFoundError("Keyboard backlight brightness control is not supported on this system.")

    brightness_path.write_text(f"{brightness}\n", encoding="utf-8")
    if rgb_state_path.exists() and rgb_mode_path.exists():
        red = int(color[1:3], 16)
        green = int(color[3:5], 16)
        blue = int(color[5:7], 16)
        rgb_state_path.write_text("1 1 1 0 1\n", encoding="utf-8")
        rgb_mode_path.write_text(
            f"1 {KEYBOARD_LIGHTING_MODE_MAP[mode]} {red} {green} {blue} {KEYBOARD_LIGHTING_SPEED_MAP[speed]}\n",
            encoding="utf-8",
        )


def _keyboard_lighting_payload(state: dict) -> dict:
    status = read_keyboard_lighting_status(state)
    return {
        "supported": status.supported,
        "brightness": status.brightness,
        "max_brightness": status.max_brightness,
        "rgb_supported": status.rgb_supported,
        "selected_mode": status.selected_mode,
        "selected_color": status.selected_color,
        "selected_speed": status.selected_speed,
        "last_applied": state.get("last_applied_keyboard_lighting"),
    }


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
        "cpu_clock": {
            **_cpu_clock_payload(),
            "selected_max_freq_khz": state.get("cpu_max_freq_khz"),
            "last_applied_max_freq_khz": state.get("last_applied_cpu_max_freq_khz"),
        },
        "thermal_profile": {
            **_thermal_profile_payload(),
            "selected_profile": state.get("thermal_profile"),
            "last_applied_profile": state.get("last_applied_thermal_profile"),
        },
        "keyboard_lighting": _keyboard_lighting_payload(state),
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


def command_set_cpu_max(args: argparse.Namespace) -> int:
    _require_root()
    freq_khz = int(args.freq_khz)
    _write_cpu_max_freq(freq_khz)

    state = load_state()
    state["cpu_max_freq_khz"] = freq_khz
    state["last_applied_cpu_max_freq_khz"] = freq_khz
    save_state(state)
    return command_status(args)


def command_set_thermal_profile(args: argparse.Namespace) -> int:
    _require_root()
    profile = validate_thermal_profile(args.profile)
    _write_thermal_profile(profile)

    state = load_state()
    state["thermal_profile"] = profile
    state["last_applied_thermal_profile"] = profile
    save_state(state)
    return command_status(args)


def command_set_keyboard_lighting(args: argparse.Namespace) -> int:
    _require_root()
    brightness = int(args.brightness)
    mode = validate_keyboard_mode(args.mode)
    color = validate_hex_color(args.color)
    speed = validate_keyboard_speed(args.speed)
    _write_keyboard_lighting(brightness, mode, color, speed)

    state = load_state()
    state["keyboard_brightness"] = brightness
    state["keyboard_rgb_mode"] = mode
    state["keyboard_rgb_color"] = color
    state["keyboard_rgb_speed"] = speed
    state["last_applied_keyboard_lighting"] = {
        "brightness": brightness,
        "mode": mode,
        "color": color,
        "speed": speed,
    }
    save_state(state)
    return command_status(args)


def command_enforce(_args: argparse.Namespace) -> int:
    _require_root()
    state = load_state()
    battery = read_battery_status()
    target, reverted = determine_target_threshold(state, battery.capacity)
    _write_threshold(target)
    state["last_applied_threshold"] = target
    cpu_max_freq = state.get("cpu_max_freq_khz")
    if cpu_max_freq is not None:
        _write_cpu_max_freq(int(cpu_max_freq))
        state["last_applied_cpu_max_freq_khz"] = int(cpu_max_freq)
    thermal_profile = state.get("thermal_profile")
    if thermal_profile is not None:
        _write_thermal_profile(thermal_profile)
        state["last_applied_thermal_profile"] = thermal_profile
    keyboard_brightness = state.get("keyboard_brightness")
    if keyboard_brightness is not None:
        _write_keyboard_lighting(
            int(keyboard_brightness),
            state["keyboard_rgb_mode"],
            state["keyboard_rgb_color"],
            state["keyboard_rgb_speed"],
        )
        state["last_applied_keyboard_lighting"] = {
            "brightness": int(keyboard_brightness),
            "mode": state["keyboard_rgb_mode"],
            "color": state["keyboard_rgb_color"],
            "speed": state["keyboard_rgb_speed"],
        }
    save_state(state)

    payload = {
        "battery_percent": battery.capacity,
        "charging_status": battery.charging_status,
        "selected_threshold": state["selected_threshold"],
        "temporary_full": state["temporary_full"],
        "effective_target": target,
        "reverted_to_default": reverted,
        "cpu_clock": {
            **_cpu_clock_payload(),
            "selected_max_freq_khz": state.get("cpu_max_freq_khz"),
            "last_applied_max_freq_khz": state.get("last_applied_cpu_max_freq_khz"),
        },
        "thermal_profile": {
            **_thermal_profile_payload(),
            "selected_profile": state.get("thermal_profile"),
            "last_applied_profile": state.get("last_applied_thermal_profile"),
        },
        "keyboard_lighting": _keyboard_lighting_payload(state),
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

    set_cpu_max = subparsers.add_parser("set-cpu-max", help="Set the CPU maximum clock speed in kHz")
    set_cpu_max.add_argument("freq_khz", type=int)
    set_cpu_max.set_defaults(func=command_set_cpu_max)

    set_thermal_profile = subparsers.add_parser("set-thermal-profile", help="Set the laptop thermal profile")
    set_thermal_profile.add_argument("profile", choices=("silent", "balanced", "turbo"))
    set_thermal_profile.set_defaults(func=command_set_thermal_profile)

    set_keyboard_lighting = subparsers.add_parser("set-keyboard-lighting", help="Set keyboard lighting")
    set_keyboard_lighting.add_argument("--brightness", type=int, required=True)
    set_keyboard_lighting.add_argument("--mode", choices=("static", "rainbow", "flashing", "glow"), required=True)
    set_keyboard_lighting.add_argument("--color", required=True)
    set_keyboard_lighting.add_argument("--speed", choices=("slow", "medium", "fast"), required=True)
    set_keyboard_lighting.set_defaults(func=command_set_keyboard_lighting)

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
