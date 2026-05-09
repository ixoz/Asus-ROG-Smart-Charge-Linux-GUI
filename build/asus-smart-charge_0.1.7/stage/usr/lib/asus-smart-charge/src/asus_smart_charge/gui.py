from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import gi

from asus_smart_charge import APP_ID, APP_NAME
from asus_smart_charge.common import KEYBOARD_LIGHTING_MODES, KEYBOARD_LIGHTING_SPEEDS, THERMAL_PROFILES, VALID_THRESHOLDS

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402


HELPER_PATH = "/usr/lib/asus-smart-charge/asus-smart-charge-helper"


def dev_helper_command() -> list[str]:
    project_root = Path(__file__).resolve().parents[2]
    return [sys.executable, "-m", "asus_smart_charge.helper"]


def installed_helper_command() -> list[str]:
    return [HELPER_PATH]


class ThresholdRow(Adw.ActionRow):
    def __init__(self, threshold: int, on_selected):
        super().__init__()
        self.threshold = threshold
        self.set_title(f"{threshold}%")
        self.set_subtitle("Always use this as the normal charge cap.")
        self.check = Gtk.CheckButton()
        self.check.connect("toggled", self._on_toggled, on_selected)
        self.add_prefix(self.check)
        self.set_activatable_widget(self.check)

    def _on_toggled(self, button: Gtk.CheckButton, on_selected):
        if button.get_active():
            on_selected(self.threshold)

    def set_group(self, leader: Gtk.CheckButton) -> None:
        self.check.set_group(leader)

    def set_selected(self, active: bool) -> None:
        self.check.set_active(active)


class ThermalProfileRow(Adw.ActionRow):
    PROFILE_TITLES = {
        "silent": "Silent",
        "balanced": "Balanced",
        "turbo": "Turbo",
    }
    PROFILE_SUBTITLES = {
        "silent": "Lowest fan noise; on supported ASUS firmware the fans can stop at low temperatures.",
        "balanced": "Default everyday fan and performance behavior.",
        "turbo": "Maximum cooling and performance behavior.",
    }

    def __init__(self, profile: str, on_selected):
        super().__init__()
        self.profile = profile
        self.set_title(self.PROFILE_TITLES.get(profile, profile.title()))
        self.set_subtitle(self.PROFILE_SUBTITLES.get(profile, ""))
        self.check = Gtk.CheckButton()
        self.check.connect("toggled", self._on_toggled, on_selected)
        self.add_prefix(self.check)
        self.set_activatable_widget(self.check)

    def _on_toggled(self, button: Gtk.CheckButton, on_selected):
        if button.get_active():
            on_selected(self.profile)

    def set_group(self, leader: Gtk.CheckButton) -> None:
        self.check.set_group(leader)

    def set_selected(self, active: bool) -> None:
        self.check.set_active(active)

    def set_profile_available(self, available: bool) -> None:
        self.set_sensitive(available)


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application):
        super().__init__(application=app, title=APP_NAME)
        self.set_default_size(560, 760)

        self.threshold_rows: list[ThresholdRow] = []
        self.thermal_profile_rows: list[ThermalProfileRow] = []
        self.nav_buttons: dict[str, Gtk.ToggleButton] = {}
        self.refresh_source_id = 0
        self.cpu_temperature_refresh_source_id = 0
        self.keyboard_refresh_source_id = 0
        self.keyboard_apply_source_id = 0
        self.ignore_selection_changes = False
        self.ignore_thermal_profile_changes = False
        self.ignore_nav_changes = False
        self.ignore_cpu_clock_changes = False
        self.ignore_keyboard_lighting_changes = False
        self.cpu_min_freq_khz: int | None = None
        self.cpu_max_freq_khz: int | None = None
        self.keyboard_max_brightness = 3
        self.status_label = Gtk.Label(xalign=0)
        self.status_label.add_css_class("title-3")
        self.detail_label = Gtk.Label(xalign=0, wrap=True)
        self.detail_label.add_css_class("dim-label")
        self.message_label = Gtk.Label(xalign=0, wrap=True)
        self.message_label.add_css_class("caption")
        self.charge_once_button = Gtk.Button(label="Charge To 100% Once")
        self.charge_once_button.add_css_class("suggested-action")
        self.charge_once_button.connect("clicked", self.on_charge_once_clicked)
        self.cpu_clock_label = Gtk.Label(xalign=0)
        self.cpu_clock_label.add_css_class("heading")
        self.cpu_temperature_label = Gtk.Label(xalign=0)
        self.cpu_temperature_label.add_css_class("title-3")
        self.cpu_clock_detail_label = Gtk.Label(xalign=0, wrap=True)
        self.cpu_clock_detail_label.add_css_class("dim-label")
        self.cpu_clock_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1.0, 4.2, 0.1)
        self.cpu_clock_scale.set_hexpand(True)
        self.cpu_clock_scale.set_digits(1)
        self.cpu_clock_scale.set_draw_value(False)
        self.cpu_clock_scale.connect("value-changed", self.on_cpu_clock_scale_changed)
        self.cpu_clock_apply_button = Gtk.Button(label="Apply")
        self.cpu_clock_apply_button.add_css_class("suggested-action")
        self.cpu_clock_apply_button.connect("clicked", self.on_cpu_clock_apply_clicked)
        self.keyboard_status_label = Gtk.Label(xalign=0)
        self.keyboard_status_label.add_css_class("title-3")
        self.keyboard_detail_label = Gtk.Label(xalign=0, wrap=True)
        self.keyboard_detail_label.add_css_class("dim-label")
        self.keyboard_brightness_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 3, 1)
        self.keyboard_brightness_scale.set_hexpand(True)
        self.keyboard_brightness_scale.set_digits(0)
        self.keyboard_brightness_scale.set_draw_value(False)
        self.keyboard_brightness_scale.connect("value-changed", self.on_keyboard_lighting_changed)
        self.keyboard_mode_combo = Gtk.ComboBoxText()
        for mode in KEYBOARD_LIGHTING_MODES:
            self.keyboard_mode_combo.append(mode, mode.title())
        self.keyboard_mode_combo.connect("changed", self.on_keyboard_lighting_changed)
        self.keyboard_speed_combo = Gtk.ComboBoxText()
        for speed in KEYBOARD_LIGHTING_SPEEDS:
            self.keyboard_speed_combo.append(speed, speed.title())
        self.keyboard_speed_combo.connect("changed", self.on_keyboard_lighting_changed)
        self.keyboard_color_button = Gtk.ColorButton()
        self.keyboard_color_button.connect("color-set", self.on_keyboard_lighting_changed)

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)

        refresh_button = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh_button.set_tooltip_text("Refresh")
        refresh_button.connect("clicked", lambda *_: self.refresh_status())
        header.pack_end(refresh_button)

        shell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        shell.set_margin_top(18)
        shell.set_margin_bottom(24)
        shell.set_margin_start(24)
        shell.set_margin_end(24)

        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        nav.add_css_class("linked")
        battery_nav = self.create_nav_button("battery", "battery-good-symbolic", "Battery")
        cpu_nav = self.create_nav_button("cpu", "computer-chip-symbolic", "CPU")
        fan_nav = self.create_nav_button("fan", "weather-windy-symbolic", "Fan")
        keyboard_nav = self.create_nav_button("keyboard", "input-keyboard-symbolic", "Keyboard")
        cpu_nav.set_group(battery_nav)
        fan_nav.set_group(battery_nav)
        keyboard_nav.set_group(battery_nav)
        nav.append(battery_nav)
        nav.append(cpu_nav)
        nav.append(fan_nav)
        nav.append(keyboard_nav)
        shell.append(nav)

        stack = Gtk.Stack()
        stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        stack.set_transition_duration(180)
        stack.set_vexpand(True)
        self.stack = stack

        battery_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)

        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        title = Gtk.Label(label="Battery Threshold", xalign=0)
        title.add_css_class("title-1")
        hero.append(title)
        hero.append(self.status_label)
        hero.append(self.detail_label)
        battery_page.append(hero)

        thresholds_group = Adw.PreferencesGroup(title="Default Limit")
        group_leader = None
        for threshold in VALID_THRESHOLDS:
            row = ThresholdRow(threshold, self.on_threshold_selected)
            if group_leader is None:
                group_leader = row.check
            else:
                row.set_group(group_leader)
            thresholds_group.add(row)
            self.threshold_rows.append(row)
        battery_page.append(thresholds_group)

        actions_group = Adw.PreferencesGroup(title="Quick Action")
        action_row = Adw.ActionRow(
            title="Fill To 100% One Time",
            subtitle="The app will return to your usual limit after the battery reaches full.",
        )
        action_row.add_suffix(self.charge_once_button)
        actions_group.add(action_row)
        battery_page.append(actions_group)

        cpu_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)

        cpu_hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        cpu_title = Gtk.Label(label="CPU Clock", xalign=0)
        cpu_title.add_css_class("title-1")
        cpu_hero.append(cpu_title)
        cpu_hero.append(self.cpu_temperature_label)
        cpu_hero.append(self.cpu_clock_label)
        cpu_hero.append(self.cpu_clock_detail_label)
        cpu_page.append(cpu_hero)

        cpu_group = Adw.PreferencesGroup(title="Clock Limit")
        cpu_group.set_description("Lower the maximum CPU clock to reduce heat, fan noise, and power use.")
        cpu_row = Adw.PreferencesRow()
        cpu_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        cpu_box.set_margin_top(12)
        cpu_box.set_margin_bottom(12)
        cpu_box.set_margin_start(12)
        cpu_box.set_margin_end(12)
        cpu_controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        cpu_controls.append(self.cpu_clock_scale)
        cpu_controls.append(self.cpu_clock_apply_button)
        cpu_box.append(cpu_controls)
        cpu_row.set_child(cpu_box)
        cpu_group.add(cpu_row)
        cpu_page.append(cpu_group)

        fan_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)

        fan_hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        fan_title = Gtk.Label(label="Fan Mode", xalign=0)
        fan_title.add_css_class("title-1")
        fan_detail = Gtk.Label(label="Choose the ASUS firmware performance profile.", xalign=0, wrap=True)
        fan_detail.add_css_class("dim-label")
        fan_hero.append(fan_title)
        fan_hero.append(fan_detail)
        fan_page.append(fan_hero)

        thermal_group = Adw.PreferencesGroup(title="Fan / Performance Mode")
        thermal_group.set_description("Uses your ASUS firmware profiles: Silent, Balanced, and Turbo.")
        thermal_group_leader = None
        for profile in THERMAL_PROFILES:
            row = ThermalProfileRow(profile, self.on_thermal_profile_selected)
            if thermal_group_leader is None:
                thermal_group_leader = row.check
            else:
                row.set_group(thermal_group_leader)
            thermal_group.add(row)
            self.thermal_profile_rows.append(row)
        fan_page.append(thermal_group)

        keyboard_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)

        keyboard_hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        keyboard_title = Gtk.Label(label="Keyboard Lighting", xalign=0)
        keyboard_title.add_css_class("title-1")
        keyboard_hero.append(keyboard_title)
        keyboard_hero.append(self.keyboard_status_label)
        keyboard_hero.append(self.keyboard_detail_label)
        keyboard_page.append(keyboard_hero)

        keyboard_group = Adw.PreferencesGroup(title="Lighting")
        brightness_row = Adw.PreferencesRow()
        brightness_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        brightness_box.set_margin_top(12)
        brightness_box.set_margin_bottom(12)
        brightness_box.set_margin_start(12)
        brightness_box.set_margin_end(12)
        brightness_title = Gtk.Label(label="Brightness", xalign=0)
        brightness_title.add_css_class("heading")
        brightness_box.append(brightness_title)
        brightness_box.append(self.keyboard_brightness_scale)
        brightness_row.set_child(brightness_box)
        keyboard_group.add(brightness_row)

        mode_row = Adw.ActionRow(title="Mode")
        mode_row.add_suffix(self.keyboard_mode_combo)
        keyboard_group.add(mode_row)

        color_row = Adw.ActionRow(title="Color")
        color_row.add_suffix(self.keyboard_color_button)
        keyboard_group.add(color_row)

        speed_row = Adw.ActionRow(title="Speed")
        speed_row.add_suffix(self.keyboard_speed_combo)
        keyboard_group.add(speed_row)

        keyboard_page.append(keyboard_group)

        stack.add_named(battery_page, "battery")
        stack.add_named(cpu_page, "cpu")
        stack.add_named(fan_page, "fan")
        stack.add_named(keyboard_page, "keyboard")
        shell.append(stack)
        shell.append(self.message_label)
        self.show_page("battery")

        scroller = Gtk.ScrolledWindow()
        scroller.set_child(shell)
        toolbar.set_content(scroller)
        self.set_content(toolbar)

        self.refresh_status()
        self.refresh_source_id = GLib.timeout_add_seconds(15, self._refresh_tick)
        self.cpu_temperature_refresh_source_id = GLib.timeout_add_seconds(2, self._cpu_temperature_refresh_tick)
        self.keyboard_refresh_source_id = GLib.timeout_add_seconds(1, self._keyboard_refresh_tick)

    def create_nav_button(self, page_name: str, icon_name: str, label: str) -> Gtk.ToggleButton:
        button = Gtk.ToggleButton()
        button.set_hexpand(True)
        button.set_tooltip_text(label)
        button.connect("toggled", self.on_nav_toggled, page_name)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        content.set_margin_top(8)
        content.set_margin_bottom(8)
        icon = Gtk.Image(icon_name=icon_name)
        text = Gtk.Label(label=label)
        text.add_css_class("caption")
        content.append(icon)
        content.append(text)
        button.set_child(content)
        self.nav_buttons[page_name] = button
        return button

    def on_nav_toggled(self, button: Gtk.ToggleButton, page_name: str) -> None:
        if self.ignore_nav_changes or not button.get_active():
            return
        self.show_page(page_name)

    def show_page(self, page_name: str) -> None:
        self.stack.set_visible_child_name(page_name)
        self.ignore_nav_changes = True
        for name, button in self.nav_buttons.items():
            button.set_active(name == page_name)
        self.ignore_nav_changes = False

    def helper_command(self, require_root: bool) -> list[str]:
        if Path(HELPER_PATH).exists():
            base = installed_helper_command()
        else:
            base = dev_helper_command()
        if require_root:
            return ["pkexec", *base]
        return base

    def run_helper(self, *args: str, require_root: bool = False) -> dict:
        command = [*self.helper_command(require_root), *args]
        env = os.environ.copy()
        if "PYTHONPATH" not in env:
            project_root = Path(__file__).resolve().parents[2]
            env["PYTHONPATH"] = str(project_root / "src")
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        output = completed.stdout.strip() or "{}"
        return json.loads(output)

    def refresh_status(self) -> None:
        try:
            status = self.run_helper("status")
        except subprocess.CalledProcessError as exc:
            self.show_error(exc.stderr.strip() or "Unable to query helper status.")
            return
        except json.JSONDecodeError:
            self.show_error("The helper returned invalid data.")
            return

        selected = status["selected_threshold"]
        battery_percent = status.get("battery_percent")
        charging_status = status.get("charging_status", "Unknown")
        applied = status.get("applied_threshold")
        temporary_full = status.get("temporary_full", False)
        cpu_clock = status.get("cpu_clock", {})
        thermal_profile = status.get("thermal_profile", {})
        keyboard_lighting = status.get("keyboard_lighting", {})

        battery_text = "Battery status unavailable"
        if battery_percent is not None:
            battery_text = f"Battery at {battery_percent}%"
        self.status_label.set_label(
            f"{battery_text} | {charging_status} | Applied cap {applied if applied is not None else '?'}%"
        )
        if temporary_full:
            self.detail_label.set_label(
                f"Temporary 100% mode is active. Your normal limit will return to {selected}% after a full charge."
            )
        else:
            self.detail_label.set_label(f"Normal charging will stop at {selected}%.")

        self.ignore_selection_changes = True
        for row in self.threshold_rows:
            row.set_selected(row.threshold == selected)
        self.ignore_selection_changes = False

        self.message_label.set_label("")
        self.charge_once_button.set_sensitive(not temporary_full and selected != 100)
        self.update_thermal_profile_status(thermal_profile)
        self.update_cpu_clock_status(cpu_clock)
        self.update_keyboard_lighting_status(keyboard_lighting)

    def refresh_keyboard_lighting_status(self) -> None:
        try:
            status = self.run_helper("status")
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            return
        self.update_keyboard_lighting_status(status.get("keyboard_lighting", {}))

    def refresh_cpu_temperature_status(self) -> None:
        try:
            status = self.run_helper("status")
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            return
        self.update_cpu_temperature_status(status.get("cpu_clock", {}))

    def show_error(self, message: str) -> None:
        self.message_label.set_label(message)

    def on_threshold_selected(self, threshold: int) -> None:
        if self.ignore_selection_changes:
            return
        try:
            self.run_helper("set-default", str(threshold), require_root=True)
        except subprocess.CalledProcessError as exc:
            self.show_error(exc.stderr.strip() or "Failed to update the threshold.")
            self.refresh_status()
            return
        self.message_label.set_label(f"Default threshold updated to {threshold}%.")
        self.refresh_status()

    def on_charge_once_clicked(self, _button: Gtk.Button) -> None:
        try:
            self.run_helper("charge-once", require_root=True)
        except subprocess.CalledProcessError as exc:
            self.show_error(exc.stderr.strip() or "Failed to enable temporary full charge.")
            return
        self.message_label.set_label("Temporary 100% mode enabled.")
        self.refresh_status()

    def update_thermal_profile_status(self, thermal_profile: dict) -> None:
        supported = thermal_profile.get("supported", False)
        active_profile = thermal_profile.get("selected_profile") or thermal_profile.get("active_profile")
        available_profiles = set(thermal_profile.get("available_profiles") or [])

        self.ignore_thermal_profile_changes = True
        for row in self.thermal_profile_rows:
            row.set_profile_available(supported and row.profile in available_profiles)
            row.set_selected(row.profile == active_profile)
        self.ignore_thermal_profile_changes = False

    def on_thermal_profile_selected(self, profile: str) -> None:
        if self.ignore_thermal_profile_changes:
            return
        try:
            self.run_helper("set-thermal-profile", profile, require_root=True)
        except subprocess.CalledProcessError as exc:
            self.show_error(exc.stderr.strip() or "Failed to update the fan/performance mode.")
            self.refresh_status()
            return
        self.refresh_status()
        self.message_label.set_label(f"Fan/performance mode updated to {profile.title()}.")

    @staticmethod
    def khz_to_ghz(freq_khz: int | None) -> float | None:
        if freq_khz is None:
            return None
        return freq_khz / 1_000_000

    @staticmethod
    def format_freq(freq_khz: int | None) -> str:
        freq_ghz = MainWindow.khz_to_ghz(freq_khz)
        if freq_ghz is None:
            return "unknown"
        return f"{freq_ghz:.1f} GHz"

    @staticmethod
    def format_temperature(temperature_c: float | None) -> str:
        if temperature_c is None:
            return "unknown"
        return f"{temperature_c:.1f} C"

    def update_cpu_temperature_status(self, cpu_clock: dict) -> None:
        temperature = self.format_temperature(cpu_clock.get("temperature_c"))
        self.cpu_temperature_label.set_label(f"CPU temperature: {temperature}")

    def update_cpu_clock_status(self, cpu_clock: dict) -> None:
        supported = cpu_clock.get("supported", False)
        self.cpu_min_freq_khz = cpu_clock.get("min_freq_khz")
        self.cpu_max_freq_khz = cpu_clock.get("max_freq_khz")
        current_max = cpu_clock.get("current_max_freq_khz")
        selected_max = cpu_clock.get("selected_max_freq_khz") or current_max or self.cpu_max_freq_khz
        current_freq = cpu_clock.get("current_freq_khz")
        governor = cpu_clock.get("governor") or "unknown"
        self.update_cpu_temperature_status(cpu_clock)

        can_control = supported and self.cpu_min_freq_khz is not None and self.cpu_max_freq_khz is not None
        self.cpu_clock_scale.set_sensitive(can_control)
        self.cpu_clock_apply_button.set_sensitive(can_control)
        if not can_control:
            self.cpu_clock_label.set_label("CPU clock control is unavailable")
            self.cpu_clock_detail_label.set_label("This kernel did not expose CPUFreq controls.")
            return

        min_ghz = self.khz_to_ghz(self.cpu_min_freq_khz) or 1.0
        max_ghz = self.khz_to_ghz(self.cpu_max_freq_khz) or 4.2
        selected_ghz = self.khz_to_ghz(selected_max) or max_ghz

        self.ignore_cpu_clock_changes = True
        self.cpu_clock_scale.set_range(min_ghz, max_ghz)
        self.cpu_clock_scale.set_increments(0.1, 0.5)
        self.cpu_clock_scale.set_value(selected_ghz)
        self.ignore_cpu_clock_changes = False

        self.cpu_clock_label.set_label(f"Max CPU clock: {self.format_freq(selected_max)}")
        self.cpu_clock_detail_label.set_label(
            f"Current {self.format_freq(current_freq)} | Limit range {self.format_freq(self.cpu_min_freq_khz)}"
            f" to {self.format_freq(self.cpu_max_freq_khz)} | Governor {governor}"
        )

    def on_cpu_clock_scale_changed(self, scale: Gtk.Scale) -> None:
        if self.ignore_cpu_clock_changes:
            return
        freq_khz = int(round(scale.get_value() * 10) / 10 * 1_000_000)
        self.cpu_clock_label.set_label(f"Max CPU clock: {self.format_freq(freq_khz)}")

    def on_cpu_clock_apply_clicked(self, _button: Gtk.Button) -> None:
        freq_khz = int(round(self.cpu_clock_scale.get_value() * 10) / 10 * 1_000_000)
        try:
            self.run_helper("set-cpu-max", str(freq_khz), require_root=True)
        except subprocess.CalledProcessError as exc:
            self.show_error(exc.stderr.strip() or "Failed to update the CPU clock limit.")
            self.refresh_status()
            return
        self.refresh_status()
        self.message_label.set_label(f"CPU clock limit updated to {self.format_freq(freq_khz)}.")

    @staticmethod
    def hex_to_rgba(color: str) -> Gdk.RGBA:
        rgba = Gdk.RGBA()
        if not rgba.parse(color):
            rgba.parse("#ffffff")
        return rgba

    @staticmethod
    def rgba_to_hex(rgba: Gdk.RGBA) -> str:
        return f"#{round(rgba.red * 255):02x}{round(rgba.green * 255):02x}{round(rgba.blue * 255):02x}"

    def update_keyboard_lighting_status(self, keyboard_lighting: dict) -> None:
        supported = keyboard_lighting.get("supported", False)
        rgb_supported = keyboard_lighting.get("rgb_supported", False)
        brightness = keyboard_lighting.get("brightness")
        selected_mode = keyboard_lighting.get("selected_mode") or "static"
        selected_color = keyboard_lighting.get("selected_color") or "#ffffff"
        selected_speed = keyboard_lighting.get("selected_speed") or "medium"
        self.keyboard_max_brightness = keyboard_lighting.get("max_brightness") or 3

        self.ignore_keyboard_lighting_changes = True
        self.keyboard_brightness_scale.set_range(0, self.keyboard_max_brightness)
        self.keyboard_brightness_scale.set_increments(1, 1)
        self.keyboard_brightness_scale.set_value(brightness or 0)
        self.keyboard_mode_combo.set_active_id(selected_mode)
        self.keyboard_color_button.set_rgba(self.hex_to_rgba(selected_color))
        self.keyboard_speed_combo.set_active_id(selected_speed)
        self.ignore_keyboard_lighting_changes = False

        can_control = supported
        self.keyboard_brightness_scale.set_sensitive(can_control)
        self.keyboard_mode_combo.set_sensitive(can_control and rgb_supported)
        self.keyboard_color_button.set_sensitive(can_control and rgb_supported)
        self.keyboard_speed_combo.set_sensitive(can_control and rgb_supported)

        if not can_control:
            self.keyboard_status_label.set_label("Keyboard lighting is unavailable")
            self.keyboard_detail_label.set_label("This system did not expose ASUS keyboard backlight controls.")
            return

        self.keyboard_status_label.set_label(
            f"Brightness {int(self.keyboard_brightness_scale.get_value())}/{self.keyboard_max_brightness}"
        )
        self.keyboard_detail_label.set_label(
            f"{selected_mode.title()} | {selected_color.upper()} | {selected_speed.title()}"
        )

    def on_keyboard_lighting_changed(self, *_args) -> None:
        if self.ignore_keyboard_lighting_changes:
            return
        mode = self.keyboard_mode_combo.get_active_id() or "static"
        speed = self.keyboard_speed_combo.get_active_id() or "medium"
        color = self.rgba_to_hex(self.keyboard_color_button.get_rgba())
        self.keyboard_status_label.set_label(
            f"Brightness {int(self.keyboard_brightness_scale.get_value())}/{self.keyboard_max_brightness}"
        )
        self.keyboard_detail_label.set_label(f"{mode.title()} | {color.upper()} | {speed.title()}")
        self.schedule_keyboard_lighting_apply()

    def schedule_keyboard_lighting_apply(self) -> None:
        if self.keyboard_apply_source_id:
            GLib.source_remove(self.keyboard_apply_source_id)
        self.keyboard_apply_source_id = GLib.timeout_add(350, self.apply_keyboard_lighting)

    def apply_keyboard_lighting(self) -> bool:
        self.keyboard_apply_source_id = 0
        brightness = int(self.keyboard_brightness_scale.get_value())
        mode = self.keyboard_mode_combo.get_active_id() or "static"
        color = self.rgba_to_hex(self.keyboard_color_button.get_rgba())
        speed = self.keyboard_speed_combo.get_active_id() or "medium"
        try:
            self.run_helper(
                "set-keyboard-lighting",
                "--brightness",
                str(brightness),
                "--mode",
                mode,
                "--color",
                color,
                "--speed",
                speed,
                require_root=True,
            )
        except subprocess.CalledProcessError as exc:
            self.show_error(exc.stderr.strip() or "Failed to update keyboard lighting.")
            self.refresh_status()
            return False
        self.refresh_status()
        self.message_label.set_label("Keyboard lighting updated.")
        return False

    def _refresh_tick(self) -> bool:
        self.refresh_status()
        return True

    def _cpu_temperature_refresh_tick(self) -> bool:
        self.refresh_cpu_temperature_status()
        return True

    def _keyboard_refresh_tick(self) -> bool:
        if not self.keyboard_apply_source_id:
            self.refresh_keyboard_lighting_status()
        return True


class AsusSmartChargeApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.connect("activate", self.on_activate)

    def on_activate(self, _app: Adw.Application) -> None:
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.PREFER_LIGHT)
        window = self.props.active_window
        if window is None:
            window = MainWindow(self)
        window.present()


def main() -> int:
    app = AsusSmartChargeApp()
    return app.run(None)


if __name__ == "__main__":
    raise SystemExit(main())
