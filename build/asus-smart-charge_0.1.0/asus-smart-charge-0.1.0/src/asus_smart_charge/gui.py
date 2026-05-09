from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import gi

from asus_smart_charge import APP_ID, APP_NAME
from asus_smart_charge.common import (
    KEYBOARD_LIGHTING_MODES,
    KEYBOARD_LIGHTING_SPEEDS,
    MAX_THRESHOLD,
    MIN_CUSTOM_THRESHOLD,
    THERMAL_PROFILES,
    VALID_THRESHOLDS,
    is_fixed_threshold,
)

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402


HELPER_PATH = "/usr/lib/asus-smart-charge/asus-smart-charge-helper"
KEYBOARD_BRIGHTNESS_SETTLE_SECONDS = 2.0


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


class CustomThresholdRow(Adw.ActionRow):
    def __init__(self, on_selected):
        super().__init__()
        self.set_title("Custom")
        self.set_subtitle("Pick any battery cap in the supported range.")
        self.check = Gtk.CheckButton()
        self.check.connect("toggled", self._on_toggled, on_selected)
        self.add_prefix(self.check)
        self.set_activatable_widget(self.check)

    def _on_toggled(self, button: Gtk.CheckButton, on_selected):
        if button.get_active():
            on_selected()

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


class MetricBox(Gtk.Frame):
    def __init__(self, title: str, value: str = "unknown", detail: str = ""):
        super().__init__()
        self.set_hexpand(True)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        content.set_margin_start(14)
        content.set_margin_end(14)

        title_label = Gtk.Label(label=title, xalign=0)
        title_label.add_css_class("caption")
        self.value_label = Gtk.Label(label=value, xalign=0)
        self.value_label.add_css_class("title-2")
        self.detail_label = Gtk.Label(label=detail, xalign=0)
        self.detail_label.add_css_class("dim-label")

        content.append(title_label)
        content.append(self.value_label)
        content.append(self.detail_label)
        self.set_child(content)

    def set_metric(self, value: str, detail: str = "") -> None:
        self.value_label.set_label(value)
        self.detail_label.set_label(detail)


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application):
        super().__init__(application=app, title=APP_NAME)
        self.set_default_size(620, 780)
        self.set_size_request(480, 600)
        self.maximize()

        self.threshold_rows: list[ThresholdRow] = []
        self.custom_threshold_row: CustomThresholdRow | None = None
        self.thermal_profile_rows: list[ThermalProfileRow] = []
        self.nav_buttons: dict[str, Gtk.ToggleButton] = {}
        self.refresh_source_id = 0
        self.cpu_temperature_refresh_source_id = 0
        self.keyboard_refresh_source_id = 0
        self.ignore_selection_changes = False
        self.ignore_custom_threshold_changes = False
        self.ignore_thermal_profile_changes = False
        self.ignore_nav_changes = False
        self.ignore_cpu_clock_changes = False
        self.ignore_gpu_changes = False
        self.ignore_keyboard_lighting_changes = False
        self.keyboard_lighting_dirty = False
        self.cpu_min_freq_khz: int | None = None
        self.cpu_max_freq_khz: int | None = None
        self.keyboard_max_brightness = 3
        self.selected_threshold = 80
        self.temporary_charge_target: int | None = None
        self.status_label = Gtk.Label(xalign=0)
        self.status_label.add_css_class("title-3")
        self.detail_label = Gtk.Label(xalign=0, wrap=True)
        self.detail_label.add_css_class("dim-label")
        self.message_label = Gtk.Label(xalign=0, wrap=True)
        self.message_label.add_css_class("caption")
        self.charge_once_button = Gtk.Button(label="Charge To 100% Once")
        self.charge_once_button.add_css_class("suggested-action")
        self.charge_once_button.connect("clicked", self.on_charge_once_clicked, 100)
        self.charge_once_80_button = Gtk.Button(label="Charge To 80% Once")
        self.charge_once_80_button.connect("clicked", self.on_charge_once_clicked, 80)
        self.custom_charge_once_button = Gtk.Button(label="Custom One Time")
        self.custom_charge_once_button.connect("clicked", self.on_custom_charge_once_toggled)
        self.custom_threshold_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, MIN_CUSTOM_THRESHOLD, MAX_THRESHOLD, 1
        )
        self.custom_threshold_scale.set_hexpand(True)
        self.custom_threshold_scale.set_digits(0)
        self.custom_threshold_scale.set_draw_value(False)
        self.custom_threshold_scale.connect("value-changed", self.on_custom_threshold_scale_changed)
        self.custom_threshold_value_label = Gtk.Label(xalign=0)
        self.custom_threshold_value_label.add_css_class("caption")
        self.custom_threshold_apply_button = Gtk.Button(label="Apply Custom Limit")
        self.custom_threshold_apply_button.add_css_class("suggested-action")
        self.custom_threshold_apply_button.connect("clicked", self.on_custom_threshold_apply_clicked)
        self.custom_threshold_revealer = Gtk.Revealer()
        self.custom_threshold_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.custom_threshold_revealer.set_reveal_child(False)
        self.custom_charge_once_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, MIN_CUSTOM_THRESHOLD, MAX_THRESHOLD, 1
        )
        self.custom_charge_once_scale.set_hexpand(True)
        self.custom_charge_once_scale.set_digits(0)
        self.custom_charge_once_scale.set_draw_value(False)
        self.custom_charge_once_scale.connect("value-changed", self.on_custom_charge_once_scale_changed)
        self.custom_charge_once_value_label = Gtk.Label(xalign=0)
        self.custom_charge_once_value_label.add_css_class("caption")
        self.custom_charge_once_apply_button = Gtk.Button(label="Apply Custom Once")
        self.custom_charge_once_apply_button.add_css_class("suggested-action")
        self.custom_charge_once_apply_button.connect("clicked", self.on_custom_charge_once_apply_clicked)
        self.custom_charge_once_revealer = Gtk.Revealer()
        self.custom_charge_once_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.custom_charge_once_revealer.set_reveal_child(False)
        self.cpu_clock_label = Gtk.Label(xalign=0)
        self.cpu_clock_label.add_css_class("heading")
        self.cpu_temperature_box = MetricBox("CPU Temperature")
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
        self.fan_sensors_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.fan_sensors_box.set_homogeneous(True)
        self.gpu_status_label = Gtk.Label(xalign=0)
        self.gpu_status_label.add_css_class("title-3")
        self.gpu_detail_label = Gtk.Label(xalign=0, wrap=True)
        self.gpu_detail_label.add_css_class("dim-label")
        self.gpu_state_box = MetricBox("dGPU State")
        self.gpu_tgp_box = MetricBox("RTX 3050 TGP")
        self.gpu_display_box = MetricBox("Display Path")
        self.gpu_enable_switch = Gtk.Switch()
        self.gpu_enable_switch.set_valign(Gtk.Align.CENTER)
        self.gpu_enable_switch.connect("notify::active", self.on_gpu_enable_toggled)
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
        self.keyboard_color_chooser = Gtk.ColorChooserWidget()
        self.keyboard_color_chooser.set_use_alpha(False)
        self.keyboard_color_chooser.connect("notify::rgba", self.on_keyboard_color_changed)
        self.keyboard_apply_button = Gtk.Button(label="Apply Lighting")
        self.keyboard_apply_button.add_css_class("suggested-action")
        self.keyboard_apply_button.connect("clicked", self.on_keyboard_apply_clicked)
        self.keyboard_apply_button.set_sensitive(False)
        self._load_keyboard_color_palettes()

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
        gpu_nav = self.create_nav_button("gpu", "video-display-symbolic", "GPU")
        keyboard_nav = self.create_nav_button("keyboard", "input-keyboard-symbolic", "Keyboard")
        cpu_nav.set_group(battery_nav)
        fan_nav.set_group(battery_nav)
        gpu_nav.set_group(battery_nav)
        keyboard_nav.set_group(battery_nav)
        nav.append(battery_nav)
        nav.append(cpu_nav)
        nav.append(fan_nav)
        nav.append(gpu_nav)
        nav.append(keyboard_nav)

        nav_scroll = Gtk.ScrolledWindow()
        nav_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        nav_scroll.set_child(nav)
        nav_scroll.set_propagate_natural_width(True)
        shell.append(nav_scroll)

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
        self.custom_threshold_row = CustomThresholdRow(self.on_custom_threshold_selected)
        if group_leader is not None:
            self.custom_threshold_row.set_group(group_leader)
        thresholds_group.add(self.custom_threshold_row)
        custom_threshold_controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        custom_threshold_controls.set_margin_top(4)
        custom_threshold_controls.set_margin_bottom(12)
        custom_threshold_controls.set_margin_start(12)
        custom_threshold_controls.set_margin_end(12)
        custom_threshold_controls.append(self.custom_threshold_value_label)
        custom_threshold_controls.append(self.custom_threshold_scale)
        custom_threshold_controls.append(self.custom_threshold_apply_button)
        self.custom_threshold_revealer.set_child(custom_threshold_controls)
        custom_threshold_row = Adw.PreferencesRow()
        custom_threshold_row.set_child(self.custom_threshold_revealer)
        thresholds_group.add(custom_threshold_row)
        battery_page.append(thresholds_group)

        actions_group = Adw.PreferencesGroup(title="Quick Action")
        action_row = Adw.ActionRow(
            title="Fill To 100% One Time",
            subtitle="The app will return to your usual limit after the battery reaches full.",
        )
        action_row.add_suffix(self.charge_once_button)
        actions_group.add(action_row)
        action_80_row = Adw.ActionRow(
            title="Fill To 80% One Time",
            subtitle="Useful when you want a little more charge without going all the way to full.",
        )
        action_80_row.add_suffix(self.charge_once_80_button)
        actions_group.add(action_80_row)
        custom_once_row = Adw.ActionRow(
            title="Fill To A Custom Value One Time",
            subtitle="Choose a temporary target just for this cycle, then return to your normal limit.",
        )
        custom_once_row.add_suffix(self.custom_charge_once_button)
        actions_group.add(custom_once_row)
        custom_once_controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        custom_once_controls.set_margin_top(4)
        custom_once_controls.set_margin_bottom(12)
        custom_once_controls.set_margin_start(12)
        custom_once_controls.set_margin_end(12)
        custom_once_controls.append(self.custom_charge_once_value_label)
        custom_once_controls.append(self.custom_charge_once_scale)
        custom_once_controls.append(self.custom_charge_once_apply_button)
        self.custom_charge_once_revealer.set_child(custom_once_controls)
        custom_once_controls_row = Adw.PreferencesRow()
        custom_once_controls_row.set_child(self.custom_charge_once_revealer)
        actions_group.add(custom_once_controls_row)
        battery_page.append(actions_group)

        cpu_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)

        cpu_hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        cpu_title = Gtk.Label(label="CPU Clock", xalign=0)
        cpu_title.add_css_class("title-1")
        cpu_hero.append(cpu_title)
        cpu_hero.append(self.cpu_temperature_box)
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

        fan_sensors_group = Adw.PreferencesGroup(title="Live Fan Speed")
        fan_sensors_row = Adw.PreferencesRow()
        fan_sensors_outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        fan_sensors_outer.set_margin_top(12)
        fan_sensors_outer.set_margin_bottom(12)
        fan_sensors_outer.set_margin_start(12)
        fan_sensors_outer.set_margin_end(12)
        fan_sensors_outer.append(self.fan_sensors_box)
        fan_sensors_row.set_child(fan_sensors_outer)
        fan_sensors_group.add(fan_sensors_row)
        fan_page.append(fan_sensors_group)

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

        gpu_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)

        gpu_hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        gpu_title = Gtk.Label(label="GPU", xalign=0)
        gpu_title.add_css_class("title-1")
        gpu_hero.append(gpu_title)
        gpu_hero.append(self.gpu_status_label)
        gpu_hero.append(self.gpu_detail_label)
        gpu_page.append(gpu_hero)

        gpu_metrics_group = Adw.PreferencesGroup(title="Discrete GPU")
        gpu_metrics_row = Adw.PreferencesRow()
        gpu_metrics_outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        gpu_metrics_outer.set_margin_top(12)
        gpu_metrics_outer.set_margin_bottom(12)
        gpu_metrics_outer.set_margin_start(12)
        gpu_metrics_outer.set_margin_end(12)
        gpu_metrics = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        gpu_metrics.set_homogeneous(True)
        gpu_metrics.append(self.gpu_state_box)
        gpu_metrics.append(self.gpu_tgp_box)
        gpu_metrics.append(self.gpu_display_box)
        gpu_metrics_outer.append(gpu_metrics)
        gpu_metrics_row.set_child(gpu_metrics_outer)
        gpu_metrics_group.add(gpu_metrics_row)
        gpu_page.append(gpu_metrics_group)

        gpu_control_group = Adw.PreferencesGroup(title="Power Control")
        gpu_control_row = Adw.ActionRow(
            title="Enable NVIDIA RTX 3050",
            subtitle="Disable it to save power when AMD internal graphics is enough. USB-C display output may need it enabled.",
        )
        gpu_control_row.add_suffix(self.gpu_enable_switch)
        gpu_control_row.set_activatable_widget(self.gpu_enable_switch)
        gpu_control_group.add(gpu_control_row)
        gpu_page.append(gpu_control_group)

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

        color_row = Adw.PreferencesRow()
        color_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        color_box.set_margin_top(12)
        color_box.set_margin_bottom(12)
        color_box.set_margin_start(12)
        color_box.set_margin_end(12)
        color_title = Gtk.Label(label="Color", xalign=0)
        color_title.add_css_class("heading")
        color_hint = Gtk.Label(
            label="Pick any shade here. Changes apply while you move through the palette.",
            xalign=0,
            wrap=True,
        )
        color_hint.add_css_class("dim-label")
        color_box.append(color_title)
        color_box.append(color_hint)
        color_box.append(self.keyboard_color_chooser)
        color_row.set_child(color_box)
        keyboard_group.add(color_row)

        speed_row = Adw.ActionRow(title="Speed")
        speed_row.add_suffix(self.keyboard_speed_combo)
        keyboard_group.add(speed_row)

        apply_row = Adw.ActionRow(
            title="Apply Changes",
            subtitle="Review brightness, color, mode, and speed first, then apply once.",
        )
        apply_row.add_suffix(self.keyboard_apply_button)
        keyboard_group.add(apply_row)

        keyboard_page.append(keyboard_group)

        stack.add_named(battery_page, "battery")
        stack.add_named(cpu_page, "cpu")
        stack.add_named(fan_page, "fan")
        stack.add_named(gpu_page, "gpu")
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
        temporary_charge_target = status.get("temporary_charge_target") or 100
        cpu_clock = status.get("cpu_clock", {})
        thermal_profile = status.get("thermal_profile", {})
        gpu = status.get("gpu", {})
        keyboard_lighting = status.get("keyboard_lighting", {})

        self.selected_threshold = selected
        self.temporary_charge_target = temporary_charge_target if temporary_full else None

        battery_text = "Battery status unavailable"
        if battery_percent is not None:
            battery_text = f"Battery at {battery_percent}%"
        self.status_label.set_label(
            f"{battery_text} | {charging_status} | Applied cap {applied if applied is not None else '?'}%"
        )
        if temporary_full:
            self.detail_label.set_label(
                f"Temporary {temporary_charge_target}% mode is active. Your normal limit will return to {selected}% after this charge."
            )
        else:
            self.detail_label.set_label(f"Normal charging will stop at {selected}%.")

        self.ignore_selection_changes = True
        for row in self.threshold_rows:
            row.set_selected(row.threshold == selected)
        is_custom_threshold = not is_fixed_threshold(selected)
        if self.custom_threshold_row is not None:
            self.custom_threshold_row.set_selected(is_custom_threshold)
        self.ignore_selection_changes = False
        self.ignore_custom_threshold_changes = True
        self.custom_threshold_scale.set_value(selected)
        self.custom_charge_once_scale.set_value(
            self.temporary_charge_target if self.temporary_charge_target is not None else selected
        )
        self.ignore_custom_threshold_changes = False
        self.custom_threshold_revealer.set_reveal_child(is_custom_threshold)
        self.update_custom_threshold_value_label(selected)
        self.update_custom_charge_once_value_label(
            self.temporary_charge_target if self.temporary_charge_target is not None else selected
        )

        self.message_label.set_label("")
        actions_available = not temporary_full
        self.charge_once_button.set_sensitive(actions_available)
        self.charge_once_80_button.set_sensitive(actions_available)
        self.custom_charge_once_button.set_sensitive(actions_available)
        self.custom_charge_once_apply_button.set_sensitive(actions_available)
        self.update_thermal_profile_status(thermal_profile)
        self.update_cpu_clock_status(cpu_clock)
        self.update_gpu_status(gpu)
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
        self.update_fan_speed_status(status.get("thermal_profile", {}).get("fan_speeds", []))

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

    def on_custom_threshold_selected(self) -> None:
        if self.ignore_selection_changes or self.ignore_custom_threshold_changes:
            return
        self.custom_threshold_revealer.set_reveal_child(True)

    def on_custom_threshold_scale_changed(self, scale: Gtk.Scale) -> None:
        threshold = int(round(scale.get_value()))
        self.update_custom_threshold_value_label(threshold)
        if self.ignore_custom_threshold_changes:
            return
        if self.custom_threshold_row is not None and not self.custom_threshold_row.check.get_active():
            self.custom_threshold_row.set_selected(True)

    def on_custom_threshold_apply_clicked(self, _button: Gtk.Button) -> None:
        threshold = int(round(self.custom_threshold_scale.get_value()))
        self.apply_default_threshold(threshold)

    def update_custom_threshold_value_label(self, threshold: int) -> None:
        self.custom_threshold_value_label.set_label(f"Custom limit: {threshold}%")

    def apply_default_threshold(self, threshold: int) -> None:
        try:
            self.run_helper("set-default", str(threshold), require_root=True)
        except subprocess.CalledProcessError as exc:
            self.show_error(exc.stderr.strip() or "Failed to update the threshold.")
            self.refresh_status()
            return
        self.message_label.set_label(f"Default threshold updated to {threshold}%.")
        self.refresh_status()

    def on_charge_once_clicked(self, _button: Gtk.Button, threshold: int) -> None:
        try:
            self.run_helper("charge-once", str(threshold), require_root=True)
        except subprocess.CalledProcessError as exc:
            self.show_error(exc.stderr.strip() or "Failed to enable temporary charge mode.")
            return
        self.message_label.set_label(f"Temporary {threshold}% mode enabled.")
        self.refresh_status()

    def on_custom_charge_once_toggled(self, _button: Gtk.Button) -> None:
        reveal = not self.custom_charge_once_revealer.get_reveal_child()
        threshold = self.temporary_charge_target if self.temporary_charge_target is not None else self.selected_threshold
        self.ignore_custom_threshold_changes = True
        self.custom_charge_once_scale.set_value(threshold)
        self.ignore_custom_threshold_changes = False
        self.update_custom_charge_once_value_label(threshold)
        self.custom_charge_once_revealer.set_reveal_child(reveal)

    def on_custom_charge_once_scale_changed(self, scale: Gtk.Scale) -> None:
        threshold = int(round(scale.get_value()))
        self.update_custom_charge_once_value_label(threshold)

    def update_custom_charge_once_value_label(self, threshold: int) -> None:
        self.custom_charge_once_value_label.set_label(f"Custom one-time target: {threshold}%")

    def on_custom_charge_once_apply_clicked(self, _button: Gtk.Button) -> None:
        threshold = int(round(self.custom_charge_once_scale.get_value()))
        try:
            self.run_helper("charge-once", str(threshold), require_root=True)
        except subprocess.CalledProcessError as exc:
            self.show_error(exc.stderr.strip() or "Failed to enable custom temporary charge mode.")
            return
        self.custom_charge_once_revealer.set_reveal_child(False)
        self.message_label.set_label(f"Temporary {threshold}% mode enabled.")
        self.refresh_status()

    def update_thermal_profile_status(self, thermal_profile: dict) -> None:
        supported = thermal_profile.get("supported", False)
        active_profile = thermal_profile.get("selected_profile") or thermal_profile.get("active_profile")
        available_profiles = set(thermal_profile.get("available_profiles") or [])
        self.update_fan_speed_status(thermal_profile.get("fan_speeds", []))

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

    @staticmethod
    def format_rpm(rpm: int | None) -> str:
        if rpm is None:
            return "unknown"
        return f"{rpm:,} RPM"

    def update_cpu_temperature_status(self, cpu_clock: dict) -> None:
        temperature = self.format_temperature(cpu_clock.get("temperature_c"))
        self.cpu_temperature_box.set_metric(temperature, "Live sensor")

    def update_fan_speed_status(self, fan_speeds: list[dict]) -> None:
        while child := self.fan_sensors_box.get_first_child():
            self.fan_sensors_box.remove(child)

        if not fan_speeds:
            self.fan_sensors_box.append(MetricBox("Fans", "unavailable", "No RPM sensors found"))
            return

        for fan in fan_speeds:
            self.fan_sensors_box.append(
                MetricBox(
                    str(fan.get("name") or "Fan"),
                    self.format_rpm(fan.get("rpm")),
                    "Live RPM",
                )
            )

    def update_gpu_status(self, gpu: dict) -> None:
        supported = gpu.get("supported", False)
        enabled = gpu.get("enabled")
        model = gpu.get("model") or "NVIDIA dGPU"
        runtime_status = gpu.get("runtime_status") or "unknown"
        base_watts = gpu.get("base_watts")
        dynamic_boost_watts = gpu.get("dynamic_boost_watts")
        max_tgp_watts = gpu.get("max_tgp_watts")

        self.ignore_gpu_changes = True
        self.gpu_enable_switch.set_active(bool(enabled))
        self.ignore_gpu_changes = False
        self.gpu_enable_switch.set_sensitive(supported)

        if not supported:
            self.gpu_status_label.set_label("Discrete GPU control is unavailable")
            self.gpu_detail_label.set_label("This system did not expose ASUS dGPU disable control.")
            self.gpu_state_box.set_metric("unavailable", "ASUS control missing")
            self.gpu_tgp_box.set_metric("75 W", "RTX 3050 known maximum")
            self.gpu_display_box.set_metric("AMD iGPU", "Internal panel")
            return

        state_text = "Enabled" if enabled else "Disabled"
        self.gpu_status_label.set_label(f"{model}: {state_text}")
        self.gpu_detail_label.set_label(
            "Internal display stays on AMD graphics. USB-C display output may depend on the NVIDIA GPU."
        )
        self.gpu_state_box.set_metric(state_text, f"Runtime {runtime_status}")
        self.gpu_tgp_box.set_metric(
            f"{max_tgp_watts} W" if max_tgp_watts is not None else "unknown",
            f"{base_watts} W base + {dynamic_boost_watts} W boost"
            if base_watts is not None and dynamic_boost_watts is not None
            else "Configured variant",
        )
        self.gpu_display_box.set_metric("AMD + USB-C", "RTX needed for Type-C output")

    def on_gpu_enable_toggled(self, switch: Gtk.Switch, _param) -> None:
        if self.ignore_gpu_changes:
            return
        enabled = switch.get_active()
        try:
            self.run_helper("set-gpu", "enabled" if enabled else "disabled", require_root=True)
        except subprocess.CalledProcessError as exc:
            self.show_error(exc.stderr.strip() or "Failed to update GPU mode.")
            self.refresh_status()
            return
        self.refresh_status()
        self.message_label.set_label(f"NVIDIA GPU {'enabled' if enabled else 'disabled'}.")

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

    @staticmethod
    def hex_list_to_rgba(colors: list[str]) -> list[Gdk.RGBA]:
        rgba_colors: list[Gdk.RGBA] = []
        for color in colors:
            rgba = Gdk.RGBA()
            if rgba.parse(color):
                rgba_colors.append(rgba)
        return rgba_colors

    def _load_keyboard_color_palettes(self) -> None:
        palettes = [
            ["#fff5f5", "#fed7d7", "#fc8181", "#e53e3e", "#9b2c2c"],
            ["#fffaf0", "#feebc8", "#f6ad55", "#dd6b20", "#9c4221"],
            ["#fffff0", "#fefcbf", "#f6e05e", "#d69e2e", "#975a16"],
            ["#f0fff4", "#c6f6d5", "#68d391", "#38a169", "#22543d"],
            ["#ebf8ff", "#bee3f8", "#63b3ed", "#3182ce", "#2a4365"],
            ["#faf5ff", "#e9d8fd", "#b794f4", "#805ad5", "#44337a"],
            ["#f7fafc", "#e2e8f0", "#a0aec0", "#4a5568", "#1a202c"],
        ]
        for colors in palettes:
            self.keyboard_color_chooser.add_palette(
                Gtk.Orientation.HORIZONTAL,
                len(colors),
                self.hex_list_to_rgba(colors),
            )

    def _update_keyboard_preview_labels(self) -> None:
        mode = self.keyboard_mode_combo.get_active_id() or "static"
        speed = self.keyboard_speed_combo.get_active_id() or "medium"
        color = self.rgba_to_hex(self.keyboard_color_chooser.get_rgba())
        self.keyboard_status_label.set_label(
            f"Brightness {int(self.keyboard_brightness_scale.get_value())}/{self.keyboard_max_brightness}"
        )
        self.keyboard_detail_label.set_label(f"{mode.title()} | {color.upper()} | {speed.title()}")

    @staticmethod
    def _should_prefer_saved_keyboard_brightness(keyboard_lighting: dict, max_brightness: int) -> bool:
        hardware_brightness = keyboard_lighting.get("brightness")
        saved_brightness = keyboard_lighting.get("saved_brightness")
        last_applied = keyboard_lighting.get("last_applied")
        last_updated_at = keyboard_lighting.get("last_updated_at")
        if (
            saved_brightness is None
            or hardware_brightness is None
            or saved_brightness == hardware_brightness
            or hardware_brightness != max_brightness
            or not isinstance(last_applied, dict)
            or last_applied.get("brightness") != saved_brightness
            or not last_updated_at
        ):
            return False
        try:
            updated_at = datetime.fromisoformat(last_updated_at)
        except ValueError:
            return False
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - updated_at.astimezone(timezone.utc)).total_seconds()
        return 0 <= age_seconds <= KEYBOARD_BRIGHTNESS_SETTLE_SECONDS

    def update_keyboard_lighting_status(self, keyboard_lighting: dict) -> None:
        if self.keyboard_lighting_dirty:
            return
        supported = keyboard_lighting.get("supported", False)
        rgb_supported = keyboard_lighting.get("rgb_supported", False)
        hardware_brightness = keyboard_lighting.get("brightness")
        saved_brightness = keyboard_lighting.get("saved_brightness")
        selected_mode = keyboard_lighting.get("selected_mode") or "static"
        selected_color = keyboard_lighting.get("selected_color") or "#ffffff"
        selected_speed = keyboard_lighting.get("selected_speed") or "medium"
        self.keyboard_max_brightness = keyboard_lighting.get("max_brightness") or 3
        brightness = hardware_brightness
        if self._should_prefer_saved_keyboard_brightness(keyboard_lighting, self.keyboard_max_brightness):
            brightness = saved_brightness
        elif brightness is None:
            brightness = saved_brightness

        self.ignore_keyboard_lighting_changes = True
        self.keyboard_brightness_scale.set_range(0, self.keyboard_max_brightness)
        self.keyboard_brightness_scale.set_increments(1, 1)
        self.keyboard_brightness_scale.set_value(brightness if brightness is not None else 0)
        self.keyboard_mode_combo.set_active_id(selected_mode)
        self.keyboard_color_chooser.set_rgba(self.hex_to_rgba(selected_color))
        self.keyboard_speed_combo.set_active_id(selected_speed)
        self.ignore_keyboard_lighting_changes = False

        can_control = supported
        self.keyboard_brightness_scale.set_sensitive(can_control)
        self.keyboard_mode_combo.set_sensitive(can_control and rgb_supported)
        self.keyboard_color_chooser.set_sensitive(can_control and rgb_supported)
        self.keyboard_speed_combo.set_sensitive(can_control and rgb_supported)
        self.keyboard_apply_button.set_sensitive(False)

        if not can_control:
            self.keyboard_status_label.set_label("Keyboard lighting is unavailable")
            self.keyboard_detail_label.set_label("This system did not expose ASUS keyboard backlight controls.")
            return

        self._update_keyboard_preview_labels()

    def on_keyboard_lighting_changed(self, *_args) -> None:
        if self.ignore_keyboard_lighting_changes:
            return
        self._update_keyboard_preview_labels()
        self.mark_keyboard_lighting_dirty()

    def on_keyboard_color_changed(self, *_args) -> None:
        if self.ignore_keyboard_lighting_changes:
            return
        self._update_keyboard_preview_labels()
        self.mark_keyboard_lighting_dirty()

    def mark_keyboard_lighting_dirty(self) -> None:
        self.keyboard_lighting_dirty = True
        self.keyboard_apply_button.set_sensitive(True)

    def on_keyboard_apply_clicked(self, _button: Gtk.Button) -> None:
        brightness = int(self.keyboard_brightness_scale.get_value())
        mode = self.keyboard_mode_combo.get_active_id() or "static"
        color = self.rgba_to_hex(self.keyboard_color_chooser.get_rgba())
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
            return
        self.keyboard_lighting_dirty = False
        self.keyboard_apply_button.set_sensitive(False)
        self.refresh_status()
        self.message_label.set_label("Keyboard lighting updated.")

    def _refresh_tick(self) -> bool:
        self.refresh_status()
        return True

    def _cpu_temperature_refresh_tick(self) -> bool:
        self.refresh_cpu_temperature_status()
        return True

    def _keyboard_refresh_tick(self) -> bool:
        if not self.keyboard_lighting_dirty:
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
