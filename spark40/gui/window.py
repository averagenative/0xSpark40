"""Main window: the Spark's signal chain on one screen, kept in sync with the amp.

Top to bottom it follows the signal: noise gate, compressor, and drive; the amp beside the
recording level; modulation, delay, and reverb; then the four stored presets.
"""

from __future__ import annotations

import copy

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk, Pango  # noqa: E402

from .. import catalog, log  # noqa: E402
from ..preset import Pedal  # noqa: E402
from ..protocol import firmware_text  # noqa: E402
from . import settings, themes  # noqa: E402
from .console import ConsoleWindow  # noqa: E402
from .indicators import LinkLight  # noqa: E402
from .knob import Knob, StepSetting  # noqa: E402
from .status import ApplyStatus  # noqa: E402
from .worker import SparkState, SparkWorker  # noqa: E402

try:
    from .meter import CLIP_DB, DB_MIN, LevelMeter, LevelMonitor, find_capture_node  # noqa: E402
except (ImportError, ValueError):
    CLIP_DB, DB_MIN, LevelMonitor = -0.1, -60.0, None

    def find_capture_node():
        return None

    class LevelMeter(Gtk.Label):
        def __init__(self):
            super().__init__(label="Level meter unavailable: GStreamer isn't installed", xalign=0)
            self.add_css_class("dim-label")

        def set_levels(self, *_args):
            pass

        def reset(self):
            pass

STEPS = ["0.1", "0.2", "0.5", "1"]
HINTS = {
    "gate": "Mutes the hum between notes. A high threshold can cut off the ends of notes.",
    "comp": "Evens out picking dynamics, or adds sustain",
    "drive": "Overdrive, distortion, fuzz, or a clean boost in front of the amp",
    "amp": "The amp model and its five tone controls",
    "mod": "Chorus, flanger, phaser, tremolo, vibrato, and similar effects",
    "delay": "Echo after the amp",
    "reverb": "Room, hall, chamber, or plate reverb",
}


def card(title: str, *suffixes: Gtk.Widget, tooltip: str | None = None) -> tuple[Gtk.Box, Gtk.Box]:
    """A rounded panel with a heading row. Returns (outer, body)."""
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    outer.add_css_class("card")
    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                   margin_top=10, margin_bottom=12, margin_start=14, margin_end=14)
    header = Gtk.Box(spacing=8)
    label = Gtk.Label(label=title, xalign=0, hexpand=True)
    label.add_css_class("heading")
    if tooltip:
        label.set_tooltip_text(tooltip)
    header.append(label)
    for widget in suffixes:
        widget.set_valign(Gtk.Align.CENTER)
        header.append(widget)
    body.append(header)
    outer.append(body)
    return outer, body


class SwitchParam(Gtk.Box):
    """A parameter that is really a two-position switch on the amp, shown as a switch."""

    def __init__(self, label: str, on_change):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6, halign=Gtk.Align.CENTER,
                         valign=Gtk.Align.CENTER)
        self._on_change = on_change
        self._syncing = False
        self.switch = Gtk.Switch(halign=Gtk.Align.CENTER)
        self.switch.update_property([Gtk.AccessibleProperty.LABEL], [label])
        self.switch.connect("notify::active", self._changed)
        name = Gtk.Label(label=label)
        name.add_css_class("caption")
        self.append(self.switch)
        self.append(name)

    def _changed(self, switch, _pspec) -> None:
        if not self._syncing:
            self._on_change(1.0 if switch.get_active() else 0.0)

    def set_wire_value(self, value: float) -> None:
        self._syncing = True
        self.switch.set_active(value >= 0.5)
        self._syncing = False


class Section:
    """One block of the signal chain: on/off switch, model picker, and the model's knobs."""

    knob_size = 50

    def __init__(self, window: SparkWindow, slot: str):
        self.window = window
        self.slot = slot
        self.pedal_id: str | None = None
        self.controls: list = []
        self.models: list[catalog.Model] = []
        self._syncing = False

        self.switch = Gtk.Switch()
        self.switch.update_property([Gtk.AccessibleProperty.LABEL], [f"{catalog.SLOT_NAMES[slot]} on or off"])
        self.switch.connect("notify::active", self._enable_changed)
        self.picker = Gtk.DropDown.new_from_strings([])
        self.picker.set_enable_search(True)
        self.picker.set_expression(Gtk.PropertyExpression.new(Gtk.StringObject, None, "string"))
        self.picker.update_property([Gtk.AccessibleProperty.LABEL], [f"{catalog.SLOT_NAMES[slot]} model"])
        self.picker.connect("notify::selected", self._picked)
        self.widget, body = card(catalog.SLOT_NAMES[slot], self.picker, self.switch, tooltip=HINTS[slot])
        self.widget.set_hexpand(True)
        self.knobs = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER, homogeneous=True)
        body.append(self.knobs)
        self.extra(body)

    def extra(self, body: Gtk.Box) -> None:
        pass

    # Model list

    def set_models(self, firmware) -> None:
        self.models = catalog.for_slot(self.slot, firmware)

    def _model_names(self, pedal_id: str) -> list[str]:
        names = [m.name for m in self.models]
        if pedal_id not in [m.id for m in self.models]:
            names.append(catalog.display_name(pedal_id))
        return names

    def _show_model(self, pedal: Pedal) -> None:
        ids = [m.id for m in self.models]
        names = self._model_names(pedal.id)
        model = self.picker.get_model()
        if [model.get_string(i) for i in range(model.get_n_items())] != names:
            self.picker.set_model(Gtk.StringList.new(names))
        self.picker.set_selected(ids.index(pedal.id) if pedal.id in ids else len(names) - 1)

    def _picked(self, dropdown, _pspec) -> None:
        if self._syncing or self.pedal_id is None:
            return
        index = dropdown.get_selected()
        if index >= len(self.models):
            return
        new = self.models[index].id
        if new != self.pedal_id:
            self.window.change_model(self.slot, self.pedal_id, new)

    # On and off

    def _enable_changed(self, switch, _pspec) -> None:
        self.knobs.set_opacity(1.0 if switch.get_active() else 0.45)
        if not self._syncing and self.pedal_id:
            self.window.worker.submit("toggle", self.pedal_id, switch.get_active())

    def set_enabled(self, on: bool) -> None:
        self._syncing = True
        self.switch.set_active(on)
        self.knobs.set_opacity(1.0 if on else 0.45)
        self._syncing = False

    # Knobs

    def visible_params(self, pedal: Pedal) -> list[int]:
        model = catalog.model(pedal.id)
        count = len(model.params) if model else len(pedal.params)
        return list(range(min(count, len(pedal.params))))

    def _rebuild(self, pedal: Pedal) -> None:
        for control in self.controls:
            self.knobs.remove(control)
        self.controls = []
        model = catalog.model(pedal.id)
        for index in self.visible_params(pedal):
            param = model.params[index] if model and index < len(model.params) else None
            label = param.name if param else f"Param {index + 1}"
            send = lambda v, i=index: self.window.send_param(pedal.id, i, v)
            if param and param.switch:
                control = SwitchParam(label, send)
            else:
                control = Knob(label, send, self.window.steps, size=self.knob_size)
            control.index = index
            self.knobs.append(control)
            self.controls.append(control)

    def apply(self, pedal: Pedal) -> None:
        self._syncing = True
        if pedal.id != self.pedal_id:
            self.pedal_id = pedal.id
            self._rebuild(pedal)
        self._show_model(pedal)
        for control in self.controls:
            if control.index < len(pedal.params):
                control.set_wire_value(pedal.params[control.index])
        self._syncing = False
        self.set_enabled(pedal.on)

    def set_param(self, index: int, value: float) -> None:
        for control in self.controls:
            if control.index == index:
                control.set_wire_value(value)


class AmpSection(Section):
    knob_size = 64

    def extra(self, body: Gtk.Box) -> None:
        self.keep_knobs = Gtk.CheckButton(
            label="Keep knobs when changing amps", active=bool(self.window.prefs.get("keep_knobs", True)),
            tooltip_text="Carry Gain, Treble, Middle, Bass, and Volume over to the new amp instead of its "
                         "defaults, whether you pick the amp here or with the amp knob on the Spark",
            halign=Gtk.Align.END)
        self.keep_knobs.connect("toggled", self._keep_changed)
        body.append(self.keep_knobs)

    def _keep_changed(self, button) -> None:
        self.window.prefs["keep_knobs"] = button.get_active()
        self.window.worker.keep_knobs = button.get_active()
        settings.save(self.window.prefs)


class ReverbSection(Section):
    """Reverb is one model whose seventh parameter picks the room, so the picker shows rooms."""

    def set_models(self, firmware) -> None:
        self.models = []

    def _show_model(self, pedal: Pedal) -> None:
        model = self.picker.get_model()
        if model.get_n_items() != len(catalog.REVERB_TYPES):
            self.picker.set_model(Gtk.StringList.new(list(catalog.REVERB_TYPES)))
        if len(pedal.params) > catalog.REVERB_TYPE_PARAM:
            self.picker.set_selected(catalog.reverb_type_index(pedal.params[catalog.REVERB_TYPE_PARAM]))

    def _picked(self, dropdown, _pspec) -> None:
        if not self._syncing and self.pedal_id:
            self.window.send_param(self.pedal_id, catalog.REVERB_TYPE_PARAM, dropdown.get_selected() / 10)

    def visible_params(self, pedal: Pedal) -> list[int]:
        return list(range(min(catalog.REVERB_TYPE_PARAM, len(pedal.params))))

    def set_param(self, index: int, value: float) -> None:
        if index == catalog.REVERB_TYPE_PARAM:
            self._syncing = True
            self.picker.set_selected(catalog.reverb_type_index(value))
            self._syncing = False
        else:
            super().set_param(index, value)


class SparkWindow(Adw.ApplicationWindow):
    def __init__(self, app, on_first_state=None, worker_class=None, address: str | None = None):
        super().__init__(application=app, title="Spark 40", default_width=1280, default_height=960)
        self.prefs = settings.load()
        self.steps = StepSetting(float(self.prefs.get("knob_step", 0.2)))
        self.log = log.get("app")
        self._on_first_state = on_first_state
        self._built = False
        self._syncing = False
        self._connected = False
        self.state: SparkState | None = None
        self.monitor: LevelMonitor | None = None
        self._meter_timer = 0
        self.console: ConsoleWindow | None = None
        self.presets_dialog = None
        self.sections: dict[str, Section] = {}

        self.add_css_class("spark-window")
        if self.prefs.get("debug") and not log.debug_enabled():
            log.enable_debug(True)
        import os
        from .. import __version__
        from ..cli import paths
        self.log.info("0xSpark40 %s running from %s", __version__, os.environ.get("APPIMAGE") or "source")
        for label, path in paths():
            self.log.info("%s: %s", label, path)
        themes.manager().apply(self.prefs.get("theme", themes.DEFAULT))
        theme_action = Gio.SimpleAction.new_stateful(
            "theme", GLib.VariantType.new("s"), GLib.Variant("s", themes.current().id))
        theme_action.connect("change-state", self._theme_changed)
        self.add_action(theme_action)

        self.toasts = Adw.ToastOverlay()
        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.title_widget = Adw.WindowTitle(title="Spark 40", subtitle="Looking for the amp")
        header.set_title_widget(self.title_widget)

        presets_button = Gtk.Button(child=Adw.ButtonContent(icon_name="view-list-bullet-symbolic", label="Presets"),
                                    tooltip_text="Load, save, and back up presets")
        presets_button.connect("clicked", self._show_presets)
        header.pack_start(presets_button)
        step_box = Gtk.Box(spacing=6)
        step_label = Gtk.Label(label="Knob step")
        step_label.add_css_class("dim-label")
        self.step_toggle = Adw.ToggleGroup(
            tooltip_text="How far one scroll notch or arrow key moves a knob. Hold Shift to move by 0.1.")
        for value in STEPS:
            self.step_toggle.add(Adw.Toggle(name=value, label=value))
        current = f"{self.steps.step:g}"
        self.step_toggle.set_active_name(current if current in STEPS else "0.2")
        self.step_toggle.connect("notify::active-name", self._step_changed)
        step_box.append(step_label)
        step_box.append(self.step_toggle)
        header.pack_start(step_box)

        links = Gtk.Box(spacing=2)
        self.link_bt = LinkLight("bluetooth")
        self.link_usb = LinkLight("usb")
        links.append(self.link_bt)
        links.append(self.link_usb)
        header.pack_end(links)
        record_box = Gtk.Box(spacing=6)
        record_label = Gtk.Label(label="Record")
        record_label.add_css_class("dim-label")
        self.record_toggle = Adw.ToggleGroup(tooltip_text="What the computer records over USB")
        self.record_toggle.add(Adw.Toggle(name="amp", label="Amp", tooltip="Record the amp's processed sound"))
        self.record_toggle.add(Adw.Toggle(
            name="dry", label="Dry",
            tooltip="Switch every block off, including the amp, to record the dry guitar for reamping. "
                    "The speaker plays the dry signal too. Click Amp to switch the blocks back on."))
        self.record_toggle.set_active_name("amp")
        self.record_toggle.connect("notify::active-name", self._record_changed)
        self.record_toggle.set_sensitive(False)
        record_box.append(record_label)
        record_box.append(self.record_toggle)
        header.pack_end(record_box)

        menu = Gio.Menu()
        for group, title in themes.GROUPS.items():
            section = Gio.Menu()
            for theme in themes.THEMES:
                if theme.group == group:
                    item = Gio.MenuItem.new(theme.name, None)
                    item.set_action_and_target_value("win.theme", GLib.Variant("s", theme.id))
                    section.append_item(item)
            menu.append_section(title, section)
        header.pack_end(Gtk.MenuButton(icon_name="applications-graphics-symbolic", menu_model=menu,
                                       tooltip_text="Theme"))
        console_button = Gtk.Button(icon_name="utilities-terminal-symbolic",
                                    tooltip_text="Console: connection log and debug output")
        console_button.connect("clicked", self._show_console)
        header.pack_end(console_button)
        view.add_top_bar(header)
        self.apply_status = ApplyStatus()
        view.add_top_bar(self.apply_status)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.waiting = Adw.StatusPage(
            icon_name="audio-speakers-symbolic",
            title="Connect your Spark 40",
            description="Turn the amp on. This window finds it over Bluetooth by itself. If the Spark app on "
                        "a phone or tablet is connected to the amp, close it first.",
        )
        retry = Gtk.Button(label="Search again", halign=Gtk.Align.CENTER)
        retry.add_css_class("pill")
        retry.add_css_class("suggested-action")
        retry.connect("clicked", lambda _b: self.worker.retry())
        self.waiting.set_child(retry)
        self.stack.add_named(self.waiting, "waiting")
        self.scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
                                           vscrollbar_policy=Gtk.PolicyType.AUTOMATIC)
        self.scroller.add_css_class("spark-scroller")
        self.panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, valign=Gtk.Align.FILL,
                             margin_top=14, margin_bottom=16, margin_start=16, margin_end=16)
        self.scroller.set_child(self.panel)
        self.stack.add_named(self.scroller, "amp")
        view.set_content(self.stack)
        self.toasts.set_child(view)
        self.set_content(self.toasts)

        if worker_class is None:
            self.worker = SparkWorker(self._on_state, self._on_event, self._on_status, self._on_error,
                                      self._on_result, address)
        else:
            self.worker = worker_class(self._on_state, self._on_event, self._on_status, self._on_error,
                                       self._on_result)
        self.worker.keep_knobs = bool(self.prefs.get("keep_knobs", True))
        self._update_links()
        GLib.timeout_add_seconds(2, self._update_links)
        self.connect("close-request", self._on_close)
        self.worker.start()

    # Layout

    def _build(self) -> None:
        def row(*widgets: Gtk.Widget) -> Gtk.Box:
            box = Gtk.Box(spacing=14, homogeneous=True)
            for widget in widgets:
                box.append(widget)
            return box

        for slot in catalog.SLOTS:
            kind = {"amp": AmpSection, "reverb": ReverbSection}.get(slot, Section)
            self.sections[slot] = kind(self, slot)
        s = self.sections
        self.panel.append(row(s["gate"].widget, s["comp"].widget, s["drive"].widget))
        middle = Gtk.Box(spacing=14)
        middle.append(s["amp"].widget)
        middle.append(self._build_levels())
        self.panel.append(middle)
        self.panel.append(row(s["mod"].widget, s["delay"].widget, s["reverb"].widget))
        self.panel.append(self._build_presets())
        self.panel.append(self._build_grille())
        self._built = True

    def _build_grille(self) -> Gtk.Widget:
        """The amp's grille cloth, framed like the front of the cabinet. Only finish themes show it."""
        self.grille = Gtk.Box(height_request=120, hexpand=True, vexpand=True,
                              accessible_role=Gtk.AccessibleRole.PRESENTATION)
        self.grille.add_css_class("spark-grille")
        badge = Gtk.Label(label="0xSpark40", halign=Gtk.Align.START, valign=Gtk.Align.START,
                          margin_top=16, margin_start=18)
        badge.add_css_class("spark-badge")
        badge.add_css_class("caption")
        self.grille.append(badge)
        self.grille.set_visible(themes.current().grille is not None)
        themes.on_change(lambda theme: self.grille.set_visible(theme.grille is not None))
        return self.grille

    def _build_levels(self) -> Gtk.Widget:
        self.clip_button = Gtk.Button(label="Clipped", visible=False,
                                      tooltip_text="The recording hit full scale. Click to reset.")
        self.clip_button.add_css_class("destructive-action")
        self.clip_button.add_css_class("pill")
        self.clip_button.connect("clicked", lambda b: b.set_visible(False))
        self.peak_label = Gtk.Label(label="Peak --", xalign=1, width_chars=13)
        self.peak_label.add_css_class("numeric")
        self.peak_label.add_css_class("dim-label")
        outer, body = card("Recording level", self.clip_button, self.peak_label,
                           tooltip="What the computer records over USB. Aim for peaks between -12 and -6 dB.")
        outer.set_size_request(440, -1)
        self.meter = LevelMeter()
        body.append(self.meter)
        hint = Gtk.Label(label="The Spark records its processed sound in mono, at 48 kHz. Set the recording level "
                               "with the amp's Volume knob. Dry, in the header bar, records the guitar without "
                               "the amp and effects.", xalign=0, wrap=True)
        hint.add_css_class("caption")
        hint.add_css_class("dim-label")
        body.append(hint)
        return outer

    def _build_presets(self) -> Gtk.Widget:
        save = Gtk.Button(label="Save to preset...",
                          tooltip_text="Store the current sound in one of the amp's four presets")
        save.add_css_class("suggested-action")
        save.connect("clicked", self._ask_store)
        outer, body = card("Presets", save, tooltip="The four presets stored on the amp")
        hint = Gtk.Label(label="Click a preset to switch to it. Save to preset stores the current sound, like "
                               "holding a preset button on the amp for two seconds.", xalign=0, wrap=True)
        hint.add_css_class("caption")
        hint.add_css_class("dim-label")
        body.append(hint)
        row = Gtk.Box(spacing=8, homogeneous=True)
        self.preset_buttons = []
        for i in range(4):
            button = Gtk.Button(tooltip_text="Switch to this preset. Unsaved changes are lost.")
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=6, margin_bottom=6)
            number = Gtk.Label(label=str(i + 1))
            number.add_css_class("title-3")
            name = Gtk.Label(label=f"Preset {i + 1}", ellipsize=Pango.EllipsizeMode.END, max_width_chars=20)
            name.add_css_class("caption")
            content.append(number)
            content.append(name)
            button.set_child(content)
            button.name_label = name
            button.connect("clicked", lambda _b, n=i: self.worker.submit("select_preset", n))
            row.append(button)
            self.preset_buttons.append(button)
        body.append(row)
        return outer

    def _ask_store(self, _button) -> None:
        if self.state is None:
            self._on_error("Connect the amp to save a preset.")
            return
        names = [self.state.names[i] if i < len(self.state.names) else f"Preset {i + 1}" for i in range(4)]
        active = self.state.active if 0 <= self.state.active < 4 else 0
        slot = Adw.ComboRow(title="Preset", model=Gtk.StringList.new([f"{i + 1}: {n}" for i, n in enumerate(names)]),
                            selected=active)
        name = Adw.EntryRow(title="Name", text=self.state.current.name or "")
        rows = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        rows.add_css_class("boxed-list")
        rows.append(slot)
        rows.append(name)
        dialog = Adw.AlertDialog(
            heading="Save to a preset",
            body="This replaces the preset you pick on the amp with the current sound. The preset it replaces is "
                 "saved first, in Backups/Replaced in your presets folder.",
            extra_child=rows)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("save", "Replace preset")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def respond(_dialog, response):
            if response == "save":
                number = slot.get_selected()
                self.log.info("Saving the current sound to preset %d", number + 1)
                self.apply_status.busy(f"Saving to preset {number + 1}...")
                self.worker.submit("store_preset", number, name.get_text().strip())

        dialog.connect("response", respond)
        dialog.present(self)

    # Actions from the controls

    def send_param(self, effect: str, index: int, value: float) -> None:
        if not self._syncing:
            self.worker.set_param(effect, index, value)

    def change_model(self, slot: str, old: str, new: str) -> None:
        keep = self.sections["amp"].keep_knobs.get_active() if slot == "amp" else False
        self.log.info("Changing %s from %s to %s", slot, old, new)
        self.worker.submit("change_model", slot, old, new, keep)

    def load_preset(self, preset, name: str) -> None:
        preset = copy.deepcopy(preset)
        if self.prefs.get("keep_volume", True) and self.state is not None:
            amp, mine = preset.pedal("amp"), self.state.current.pedal("amp")
            if len(amp.params) > 4 and len(mine.params) > 4:
                amp.params[4] = mine.params[4]
        self.apply_status.busy(f"Loading '{name}'...")
        self.worker.submit("load_preset", preset, name)

    def _record_changed(self, group, _pspec) -> None:
        if not self._syncing and group.get_sensitive():
            self.worker.submit("dry", group.get_active_name() == "dry")

    # Results from the worker

    def _on_status(self, connected: bool, message: str) -> None:
        self._connected = connected
        if connected:
            self.title_widget.set_subtitle(f"Connected over {message}, reading settings")
            self._update_links()
            return
        self.state = None
        self._stop_meter()
        self._update_links()
        self.stack.set_visible_child_name("waiting")
        self.record_toggle.set_sensitive(False)
        self.title_widget.set_title("Spark 40")
        self.title_widget.set_subtitle("Not connected")
        if message:
            self.waiting.set_description(message)

    def _on_error(self, message: str) -> None:
        self.log.warning("Shown to user: %s", message)
        self.toasts.add_toast(Adw.Toast(title=message, timeout=4))

    def _subtitle(self) -> str:
        s = self.state
        fw = firmware_text(s.firmware) if s.firmware else "unknown firmware"
        parts = [f"{s.name}, firmware {fw}, {s.transport}"]
        if s.dry:
            parts.append("dry")
        elif s.edited:
            parts.append("edited")
        return ", ".join(parts)

    def _on_state(self, state: SparkState) -> None:
        if not self._built:
            self._build()
        firmware_changed = self.state is None or self.state.firmware != state.firmware
        self.state = state
        self._syncing = True
        self.title_widget.set_title(state.current.name or "Spark 40")
        self.title_widget.set_subtitle(self._subtitle())
        for slot, pedal in zip(catalog.SLOTS, state.current.pedals):
            section = self.sections[slot]
            if firmware_changed:
                section.set_models(state.firmware)
            section.apply(pedal)
        for i, button in enumerate(self.preset_buttons):
            button.name_label.set_label(state.names[i] if i < len(state.names) else f"Preset {i + 1}")
            if i == state.active and not state.edited:
                button.add_css_class("suggested-action")
            else:
                button.remove_css_class("suggested-action")
        self.record_toggle.set_active_name("dry" if state.dry else "amp")
        self.record_toggle.set_sensitive(True)
        self._syncing = False
        self.stack.set_visible_child_name("amp")
        self._start_meter_polling()
        if self._on_first_state:
            callback, self._on_first_state = self._on_first_state, None
            callback(self)

    def _on_event(self, event) -> None:
        if self.state is None:
            return
        self._syncing = True
        for slot, pedal in zip(catalog.SLOTS, self.state.current.pedals):
            if pedal.id != event.effect:
                continue
            if event.kind == "param":
                if event.index < len(pedal.params):
                    pedal.params[event.index] = event.value
                self.sections[slot].set_param(event.index, event.value)
            elif event.kind == "toggle":
                pedal.on = event.on
                self.sections[slot].set_enabled(event.on)
        self._syncing = False

    def _on_result(self, kind: str, *args) -> None:
        if kind == "edited":
            if self.state is not None:
                self.state.edited = True
                self.title_widget.set_subtitle(self._subtitle())
                for button in self.preset_buttons:
                    button.remove_css_class("suggested-action")
        elif kind == "loaded":
            self.apply_status.done(f"Loaded '{args[0]}'. Hold a preset button on the amp to keep it.")
        elif kind == "failed":
            name, message = args
            self.apply_status.done(f"Couldn't load '{name}'")
            if message:
                self._on_error(message)
        elif kind == "stored":
            number, ok, message = args
            if ok:
                self.apply_status.done(f"Saved to preset {number + 1}")
            else:
                self.apply_status.done(f"Couldn't save preset {number + 1}")
                if message:
                    self._on_error(message)
        elif kind == "saved":
            self.apply_status.done(f"Saved {args[0]}")
            if self.presets_dialog:
                self.presets_dialog.refresh()
        elif kind == "backup":
            self.apply_status.done(f"Backed up the four presets to {args[0]}")
            if self.presets_dialog:
                self.presets_dialog.refresh()

    # Header bar and window

    def _show_presets(self, _button) -> None:
        from .presets import PresetsDialog
        self.presets_dialog = PresetsDialog(self)
        self.presets_dialog.connect("closed", lambda *_: setattr(self, "presets_dialog", None))
        self.presets_dialog.present(self)

    def _show_console(self, _button) -> None:
        if self.console is None:
            self.console = ConsoleWindow(self._debug_changed)
            self.console.connect("close-request", lambda *_: setattr(self, "console", None) or False)
        self.console.present()

    def _debug_changed(self, on: bool) -> None:
        self.prefs["debug"] = on
        settings.save(self.prefs)

    def _theme_changed(self, action, value) -> None:
        action.set_state(value)
        theme = themes.manager().apply(value.get_string())
        self.prefs["theme"] = theme.id
        settings.save(self.prefs)

    def preview_theme(self, theme_id: str) -> None:
        """Show a theme without saving it as the user's choice (for --theme and screenshots)."""
        theme = themes.manager().apply(theme_id)
        self.lookup_action("theme").set_state(GLib.Variant("s", theme.id))

    def _step_changed(self, group, _pspec) -> None:
        name = group.get_active_name()
        if name:
            self.steps.step = float(name)
            self.prefs["knob_step"] = float(name)
            settings.save(self.prefs)

    def _update_links(self) -> bool:
        usb_up = find_usb_audio()
        self.link_usb.set_state(usb_up, False)
        self.link_bt.set_state(self._connected, self._connected)
        return GLib.SOURCE_CONTINUE

    def _on_close(self, *_args):
        if self.console:
            self.console.close()
        self._stop_meter()
        self.worker.stop()
        return False

    # Level meter

    def _start_meter_polling(self) -> None:
        if not self._meter_timer:
            self._meter_timer = GLib.timeout_add_seconds(2, self._ensure_meter)
        self._ensure_meter()

    def _ensure_meter(self) -> bool:
        if self.monitor is None and LevelMonitor is not None:
            node = find_capture_node()
            if node:
                self.log.info("Level meter watching %s", node)
                try:
                    self.monitor = LevelMonitor(node, self._on_level, self._on_meter_stopped)
                except Exception as err:
                    self.log.warning("Level meter unavailable: %s", err)
                    self._meter_timer = 0
                    return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def _on_level(self, peaks, holds) -> None:
        self.meter.set_levels(peaks, holds)
        hold = max(holds) if holds else DB_MIN
        self.peak_label.set_label(f"Peak {hold:.1f} dB" if hold > DB_MIN else "Peak below -60 dB")
        if max(peaks, default=DB_MIN) >= CLIP_DB:
            self.clip_button.set_visible(True)

    def _on_meter_stopped(self) -> None:
        self.monitor = None
        self.meter.reset()
        self.peak_label.set_label("Peak --")

    def _stop_meter(self) -> None:
        if self.monitor:
            self.monitor.stop()
        if self._built:
            self._on_meter_stopped()


def find_usb_audio() -> bool:
    """Whether the Spark's USB audio interface is plugged in."""
    try:
        with open("/proc/asound/cards") as cards:
            return "Spark 40 USB" in cards.read()
    except OSError:
        return False
