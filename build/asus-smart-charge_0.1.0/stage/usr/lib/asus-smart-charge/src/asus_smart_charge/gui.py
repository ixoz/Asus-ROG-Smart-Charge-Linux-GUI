from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import gi

from asus_smart_charge import APP_ID, APP_NAME
from asus_smart_charge.common import VALID_THRESHOLDS

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402


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


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application):
        super().__init__(application=app, title=APP_NAME)
        self.set_default_size(520, 520)

        self.threshold_rows: list[ThresholdRow] = []
        self.refresh_source_id = 0
        self.ignore_selection_changes = False
        self.status_label = Gtk.Label(xalign=0)
        self.status_label.add_css_class("title-3")
        self.detail_label = Gtk.Label(xalign=0, wrap=True)
        self.detail_label.add_css_class("dim-label")
        self.message_label = Gtk.Label(xalign=0, wrap=True)
        self.message_label.add_css_class("caption")
        self.charge_once_button = Gtk.Button(label="Charge To 100% Once")
        self.charge_once_button.add_css_class("suggested-action")
        self.charge_once_button.connect("clicked", self.on_charge_once_clicked)

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)

        refresh_button = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh_button.set_tooltip_text("Refresh")
        refresh_button.connect("clicked", lambda *_: self.refresh_status())
        header.pack_end(refresh_button)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        content.set_margin_top(24)
        content.set_margin_bottom(24)
        content.set_margin_start(24)
        content.set_margin_end(24)

        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        title = Gtk.Label(label="Battery Threshold", xalign=0)
        title.add_css_class("title-1")
        hero.append(title)
        hero.append(self.status_label)
        hero.append(self.detail_label)
        content.append(hero)

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
        content.append(thresholds_group)

        actions_group = Adw.PreferencesGroup(title="Quick Action")
        action_row = Adw.ActionRow(
            title="Fill To 100% One Time",
            subtitle="The app will return to your usual limit after the battery reaches full.",
        )
        action_row.add_suffix(self.charge_once_button)
        actions_group.add(action_row)
        content.append(actions_group)
        content.append(self.message_label)

        scroller = Gtk.ScrolledWindow()
        scroller.set_child(content)
        toolbar.set_content(scroller)
        self.set_content(toolbar)

        self.refresh_status()
        self.refresh_source_id = GLib.timeout_add_seconds(15, self._refresh_tick)

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

    def _refresh_tick(self) -> bool:
        self.refresh_status()
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
