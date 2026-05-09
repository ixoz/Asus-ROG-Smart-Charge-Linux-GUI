from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


APP_DIR = Path("/etc/asus-smart-charge")
STATE_FILE = APP_DIR / "state.json"
SYSFS_GLOB = "/sys/class/power_supply/BAT*/charge_control_end_threshold"
PLATFORM_PROFILE_PATH = Path("/sys/firmware/acpi/platform_profile")
PLATFORM_PROFILE_CHOICES_PATH = Path("/sys/firmware/acpi/platform_profile_choices")
ASUS_THERMAL_POLICY_PATH = Path("/sys/devices/platform/asus-nb-wmi/throttle_thermal_policy")
KBD_BACKLIGHT_PATH = Path("/sys/class/leds/asus::kbd_backlight")
VALID_THRESHOLDS = (55, 60, 70, 80, 100)
TEMP_FULL_THRESHOLD = 100
TEMP_FULL_RESET_AT = 99
THERMAL_PROFILES = ("silent", "balanced", "turbo")
KEYBOARD_LIGHTING_MODES = ("static", "rainbow", "flashing", "glow")
KEYBOARD_LIGHTING_SPEEDS = ("slow", "medium", "fast")
KEYBOARD_LIGHTING_MODE_MAP = {
    "static": 0,
    "glow": 1,
    "rainbow": 2,
    "flashing": 9,
}
KEYBOARD_LIGHTING_SPEED_MAP = {
    "slow": 0,
    "medium": 1,
    "fast": 2,
}
PLATFORM_PROFILE_MAP = {
    "silent": "quiet",
    "balanced": "balanced",
    "turbo": "performance",
}
ASUS_THERMAL_POLICY_MAP = {
    "silent": "2",
    "balanced": "0",
    "turbo": "1",
}


@dataclass
class BatteryStatus:
    battery_name: str
    threshold_path: Path
    capacity: int | None
    charging_status: str
    applied_threshold: int | None


@dataclass
class CpuClockStatus:
    supported: bool
    cpu_count: int
    min_freq_khz: int | None
    max_freq_khz: int | None
    current_max_freq_khz: int | None
    current_freq_khz: int | None
    governor: str | None
    temperature_c: float | None


@dataclass
class ThermalProfileStatus:
    supported: bool
    active_profile: str | None
    available_profiles: list[str]
    backend: str | None


@dataclass
class KeyboardLightingStatus:
    supported: bool
    brightness: int | None
    max_brightness: int | None
    rgb_supported: bool
    selected_mode: str | None
    selected_color: str | None
    selected_speed: str | None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_state() -> dict:
    return {
        "selected_threshold": 80,
        "temporary_full": False,
        "temporary_full_started_at": None,
        "last_applied_threshold": None,
        "cpu_max_freq_khz": None,
        "last_applied_cpu_max_freq_khz": None,
        "thermal_profile": None,
        "last_applied_thermal_profile": None,
        "keyboard_brightness": None,
        "keyboard_rgb_mode": "static",
        "keyboard_rgb_color": "#ffffff",
        "keyboard_rgb_speed": "medium",
        "last_applied_keyboard_lighting": None,
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
    cpu_max_freq = state.get("cpu_max_freq_khz")
    state["cpu_max_freq_khz"] = int(cpu_max_freq) if cpu_max_freq is not None else None
    thermal_profile = state.get("thermal_profile")
    if thermal_profile is not None and thermal_profile not in THERMAL_PROFILES:
        raise ValueError(f"Unsupported thermal profile in state: {thermal_profile}")
    keyboard_brightness = state.get("keyboard_brightness")
    state["keyboard_brightness"] = int(keyboard_brightness) if keyboard_brightness is not None else None
    if state.get("keyboard_rgb_mode") not in KEYBOARD_LIGHTING_MODES:
        raise ValueError(f"Unsupported keyboard lighting mode in state: {state.get('keyboard_rgb_mode')}")
    if state.get("keyboard_rgb_speed") not in KEYBOARD_LIGHTING_SPEEDS:
        raise ValueError(f"Unsupported keyboard lighting speed in state: {state.get('keyboard_rgb_speed')}")
    validate_hex_color(str(state.get("keyboard_rgb_color", "#ffffff")))
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


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError):
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


def find_cpufreq_dirs() -> list[Path]:
    return sorted(path for path in Path("/sys/devices/system/cpu").glob("cpu[0-9]*/cpufreq") if path.is_dir())


def _read_hwmon_temperature(hwmon_dir: Path, preferred_labels: tuple[str, ...] = ()) -> float | None:
    readings: list[tuple[int, float]] = []
    preferred = tuple(label.lower() for label in preferred_labels)
    for input_path in sorted(hwmon_dir.glob("temp*_input")):
        value = _read_int(input_path)
        if value is None:
            continue
        label = _read_text(input_path.with_name(input_path.name.replace("_input", "_label"))) or ""
        label_lower = label.lower()
        priority = 1
        if preferred and any(preferred_label in label_lower for preferred_label in preferred):
            priority = 0
        readings.append((priority, value / 1000))
    if not readings:
        return None
    readings.sort(key=lambda reading: (reading[0], -reading[1]))
    return round(readings[0][1], 1)


def read_cpu_temperature_c() -> float | None:
    preferred_chips = {
        "k10temp": ("tctl", "tdie"),
        "coretemp": ("package id", "core"),
        "cpu_thermal": (),
        "x86_pkg_temp": (),
        "zenpower": ("tctl", "tdie"),
    }
    fallback_temperature = None
    for hwmon_dir in sorted(Path("/sys/class/hwmon").glob("hwmon*")):
        chip_name = _read_text(hwmon_dir / "name")
        if not chip_name:
            continue
        temperature = _read_hwmon_temperature(hwmon_dir, preferred_chips.get(chip_name, ()))
        if temperature is None:
            continue
        if chip_name in preferred_chips:
            return temperature
        if chip_name == "acpitz" and fallback_temperature is None:
            fallback_temperature = temperature
    return fallback_temperature


def read_cpu_clock_status() -> CpuClockStatus:
    cpufreq_dirs = find_cpufreq_dirs()
    temperature_c = read_cpu_temperature_c()
    if not cpufreq_dirs:
        return CpuClockStatus(
            supported=False,
            cpu_count=0,
            min_freq_khz=None,
            max_freq_khz=None,
            current_max_freq_khz=None,
            current_freq_khz=None,
            governor=None,
            temperature_c=temperature_c,
        )

    cpuinfo_mins = [_read_int(path / "cpuinfo_min_freq") for path in cpufreq_dirs]
    scaling_mins = [_read_int(path / "scaling_min_freq") for path in cpufreq_dirs]
    maxes = [_read_int(path / "cpuinfo_max_freq") for path in cpufreq_dirs]
    scaling_maxes = [_read_int(path / "scaling_max_freq") for path in cpufreq_dirs]
    current_freqs = [_read_int(path / "scaling_cur_freq") for path in cpufreq_dirs]
    governors = [_read_text(path / "scaling_governor") for path in cpufreq_dirs]

    present_cpuinfo_mins = [value for value in cpuinfo_mins if value is not None]
    present_scaling_mins = [value for value in scaling_mins if value is not None]
    present_maxes = [value for value in maxes if value is not None]
    present_scaling_maxes = [value for value in scaling_maxes if value is not None]
    present_current_freqs = [value for value in current_freqs if value is not None]
    present_governors = [value for value in governors if value]

    return CpuClockStatus(
        supported=True,
        cpu_count=len(cpufreq_dirs),
        min_freq_khz=(
            max(present_scaling_mins)
            if present_scaling_mins
            else min(present_cpuinfo_mins)
            if present_cpuinfo_mins
            else None
        ),
        max_freq_khz=max(present_maxes) if present_maxes else None,
        current_max_freq_khz=min(present_scaling_maxes) if present_scaling_maxes else None,
        current_freq_khz=max(present_current_freqs) if present_current_freqs else None,
        governor=present_governors[0] if present_governors else None,
        temperature_c=temperature_c,
    )


def validate_cpu_max_freq(freq_khz: int, status: CpuClockStatus | None = None) -> int:
    status = status or read_cpu_clock_status()
    if not status.supported or status.min_freq_khz is None or status.max_freq_khz is None:
        raise FileNotFoundError("CPU clock control is not supported on this system.")
    if freq_khz < status.min_freq_khz or freq_khz > status.max_freq_khz:
        raise ValueError(
            f"CPU clock limit must be between {status.min_freq_khz} and {status.max_freq_khz} kHz."
        )
    return freq_khz


def platform_profile_to_thermal(profile: str | None) -> str | None:
    if profile is None:
        return None
    reverse = {value: key for key, value in PLATFORM_PROFILE_MAP.items()}
    return reverse.get(profile)


def asus_policy_to_thermal(policy: str | None) -> str | None:
    if policy is None:
        return None
    reverse = {value: key for key, value in ASUS_THERMAL_POLICY_MAP.items()}
    return reverse.get(policy)


def validate_thermal_profile(profile: str) -> str:
    if profile not in THERMAL_PROFILES:
        raise ValueError(f"Thermal profile must be one of {THERMAL_PROFILES}.")
    return profile


def validate_keyboard_brightness(brightness: int, max_brightness: int | None = None) -> int:
    if max_brightness is None:
        max_brightness = _read_int(KBD_BACKLIGHT_PATH / "max_brightness")
    if max_brightness is None:
        raise FileNotFoundError("Keyboard backlight brightness control is not supported on this system.")
    if brightness < 0 or brightness > max_brightness:
        raise ValueError(f"Keyboard brightness must be between 0 and {max_brightness}.")
    return brightness


def validate_keyboard_mode(mode: str) -> str:
    if mode not in KEYBOARD_LIGHTING_MODES:
        raise ValueError(f"Keyboard lighting mode must be one of {KEYBOARD_LIGHTING_MODES}.")
    return mode


def validate_keyboard_speed(speed: str) -> str:
    if speed not in KEYBOARD_LIGHTING_SPEEDS:
        raise ValueError(f"Keyboard lighting speed must be one of {KEYBOARD_LIGHTING_SPEEDS}.")
    return speed


def validate_hex_color(color: str) -> str:
    if len(color) != 7 or not color.startswith("#"):
        raise ValueError("Keyboard color must use #rrggbb format.")
    try:
        int(color[1:], 16)
    except ValueError as exc:
        raise ValueError("Keyboard color must use #rrggbb format.") from exc
    return color.lower()


def read_thermal_profile_status() -> ThermalProfileStatus:
    if PLATFORM_PROFILE_PATH.exists() and PLATFORM_PROFILE_CHOICES_PATH.exists():
        choices = (_read_text(PLATFORM_PROFILE_CHOICES_PATH) or "").split()
        available_profiles = [
            profile for profile, platform_profile in PLATFORM_PROFILE_MAP.items() if platform_profile in choices
        ]
        return ThermalProfileStatus(
            supported=bool(available_profiles),
            active_profile=platform_profile_to_thermal(_read_text(PLATFORM_PROFILE_PATH)),
            available_profiles=available_profiles,
            backend="platform_profile",
        )

    if ASUS_THERMAL_POLICY_PATH.exists():
        return ThermalProfileStatus(
            supported=True,
            active_profile=asus_policy_to_thermal(_read_text(ASUS_THERMAL_POLICY_PATH)),
            available_profiles=list(THERMAL_PROFILES),
            backend="asus_wmi",
        )

    return ThermalProfileStatus(
        supported=False,
        active_profile=None,
        available_profiles=[],
        backend=None,
    )


def read_keyboard_lighting_status(state: dict | None = None) -> KeyboardLightingStatus:
    state = state or load_state()
    brightness_path = KBD_BACKLIGHT_PATH / "brightness"
    hardware_brightness_path = KBD_BACKLIGHT_PATH / "brightness_hw_changed"
    max_brightness_path = KBD_BACKLIGHT_PATH / "max_brightness"
    rgb_mode_path = KBD_BACKLIGHT_PATH / "kbd_rgb_mode"
    rgb_state_path = KBD_BACKLIGHT_PATH / "kbd_rgb_state"
    brightness = _read_int(brightness_path)
    hardware_brightness = _read_int(hardware_brightness_path)
    if brightness is None:
        brightness = hardware_brightness
    elif hardware_brightness is not None:
        try:
            if hardware_brightness_path.stat().st_mtime_ns > brightness_path.stat().st_mtime_ns:
                brightness = hardware_brightness
        except OSError:
            pass

    return KeyboardLightingStatus(
        supported=brightness_path.exists() and max_brightness_path.exists(),
        brightness=brightness,
        max_brightness=_read_int(max_brightness_path),
        rgb_supported=rgb_mode_path.exists() and rgb_state_path.exists(),
        selected_mode=state.get("keyboard_rgb_mode"),
        selected_color=state.get("keyboard_rgb_color"),
        selected_speed=state.get("keyboard_rgb_speed"),
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
