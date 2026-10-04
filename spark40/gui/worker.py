"""Background thread that owns the Bluetooth connection so the GTK main loop never blocks.

The window submits commands; the worker runs them in order, reads the amp's change reports
between commands, and hands results back to the main loop with GLib.idle_add. Knob drags
are coalesced: only the latest value per knob is sent.
"""

from __future__ import annotations

import copy
import queue
import threading
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from gi.repository import GLib

from .. import catalog, log
from ..client import Spark, SparkError, UnsupportedModel
from ..preset import Preset

LOG = log.get("worker")

AMP_KNOBS = 5   # gain, treble, middle, bass, volume: the same five on every amp model


@dataclass
class SparkState:
    name: str
    serial: str
    firmware: tuple | None
    transport: str
    current: Preset
    active: int
    names: list = field(default_factory=list)
    edited: bool = False
    dry: bool = False


class SparkWorker(threading.Thread):
    def __init__(self, on_state, on_event, on_status, on_error, on_result=None, address: str | None = None):
        super().__init__(name="spark40-worker", daemon=True)
        self._on_state = on_state
        self._on_event = on_event
        self._on_status = on_status
        self._on_error = on_error
        self._on_result = on_result or (lambda *args: None)
        self._address = address
        self._commands: queue.Queue = queue.Queue()
        self._pending: dict = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._retry_delay = 2.0
        self._refresh_requested = False
        self._names_requested = False
        self._dry_states: list[bool] | None = None
        self.keep_knobs = True      # carry the five amp knobs over when the amp model changes
        self.spark: Spark | None = None
        self.state: SparkState | None = None

    # Called from the GTK thread

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def retry(self) -> None:
        self._retry_delay = 2.0
        self._wake.set()

    def set_param(self, effect: str, index: int, value: float) -> None:
        with self._lock:
            self._pending[(effect, index)] = value

    def submit(self, name: str, *args) -> None:
        self._commands.put((name, args))
        self._wake.set()

    # The thread

    def run(self) -> None:
        while not self._stop.is_set():
            if self.spark is None:
                if not self._connect():
                    self._wake.wait(self._retry_delay)
                    self._wake.clear()
                    self._retry_delay = min(self._retry_delay * 1.5, 15.0)
                    continue
            try:
                self._flush_params()
                self._run_commands()
                self._pump_events()
                if self._refresh_requested:
                    self._refresh_requested = False
                    self._refresh(names=self._names_requested)
                    self._names_requested = False
            except (OSError, SparkError) as err:
                LOG.warning("%s", err)
                if not self.spark.transport.alive():
                    self._disconnect(str(err))
                else:
                    GLib.idle_add(self._on_error, str(err))
            except Exception as err:
                LOG.error("Unexpected error, reconnecting:\n%s", traceback.format_exc())
                GLib.idle_add(self._on_error, f"Unexpected error: {err}. Reconnecting; see Console.")
                self._disconnect(f"Reconnecting after an error: {err}")
        if self.spark:
            self.spark.close()

    def _connect(self) -> bool:
        GLib.idle_add(self._on_status, False, "Looking for the amp over Bluetooth...")
        try:
            self.spark = Spark.open(self._address)
        except Exception as err:
            self.spark = None
            message = str(err) if isinstance(err, (SparkError, RuntimeError, OSError)) else f"Connection error: {err}"
            if message != getattr(self, "_last_error", None):
                LOG.info("Not connected: %s", message)
                self._last_error = message
            if not isinstance(err, (SparkError, RuntimeError, OSError)):
                LOG.error("Unexpected error while connecting:\n%s", traceback.format_exc())
            GLib.idle_add(self._on_status, False, message)
            return False
        self._last_error = None
        self._retry_delay = 2.0
        self._dry_states = None
        LOG.info("Connected to %s over %s", self.spark.transport.name, self.spark.transport.kind)
        GLib.idle_add(self._on_status, True, self.spark.transport.kind)
        try:
            self._refresh(names=True, identity=True)
        except Exception as err:
            LOG.warning("Couldn't read the amp's settings: %s", err)
            self._disconnect(f"Couldn't read the amp's settings: {err}")
            return False
        return True

    def _disconnect(self, reason: str) -> None:
        LOG.info("Disconnected: %s", reason)
        try:
            if self.spark:
                self.spark.close()
        except Exception:
            pass
        self.spark = None
        self.state = None
        GLib.idle_add(self._on_status, False, reason)

    def _refresh(self, names: bool = False, identity: bool = False) -> None:
        spark = self.spark
        old = self.state
        if identity or old is None:
            name, serial = spark.get_name(), spark.get_serial()
        else:
            name, serial = old.name, old.serial
        current = spark.get_current()
        active = spark.get_active_preset()
        preset_names = [spark.get_preset(n).name for n in range(4)] if names or old is None else list(old.names)
        self.state = SparkState(name=name, serial=serial, firmware=spark.firmware, transport=spark.transport.kind,
                                current=current, active=active, names=preset_names,
                                edited=bool(old and old.edited),
                                dry=self._dry_states is not None)
        GLib.idle_add(self._on_state, copy.deepcopy(self.state))

    def _flush_params(self) -> None:
        with self._lock:
            pending, self._pending = self._pending, {}
        for (effect, index), value in pending.items():
            self.spark.set_param(effect, index, value)
            self._track_param(effect, index, value)
        if pending:
            self._mark_edited()

    def _run_commands(self) -> None:
        while True:
            try:
                name, args = self._commands.get_nowait()
            except queue.Empty:
                return
            getattr(self, f"_cmd_{name}")(*args)

    def _pump_events(self) -> None:
        for event in self.spark.poll(timeout=0.04):
            if event.kind in ("param", "toggle"):
                if event.kind == "param":
                    self._track_param(event.effect, event.index, event.value)
                else:
                    self._track_toggle(event.effect, event.on)
                self._mark_edited()
                GLib.idle_add(self._on_event, event)
            elif event.kind == "preset":
                self._dry_states = None
                self._refresh_requested = True
            elif event.kind == "model":
                self._model_changed_on_amp(event.old, event.new)
                self._refresh_requested = True
            elif event.kind == "stored":
                self._refresh_requested = True
                self._names_requested = True

    # Keeping the cached settings in step

    def _pedal(self, effect: str):
        if self.state is None:
            return None
        return next((p for p in self.state.current.pedals if p.id == effect), None)

    def _track_param(self, effect: str, index: int, value: float) -> None:
        pedal = self._pedal(effect)
        if pedal is not None and index < len(pedal.params):
            pedal.params[index] = value

    def _track_toggle(self, effect: str, on: bool) -> None:
        pedal = self._pedal(effect)
        if pedal is not None:
            pedal.on = on

    def _model_changed_on_amp(self, old: str, new: str) -> None:
        """The amp's own amp selector changed the model. Like the Spark app, send the knobs back.

        The amp loads the new model's default knobs, which can be much louder. With keep_knobs on,
        the previous model's Gain, Treble, Middle, Bass, and Volume go to the new model instead.
        """
        pedal = self._pedal(old)
        if pedal is None or self.state is None or self.state.current.pedals.index(pedal) != catalog.SLOTS.index("amp"):
            return
        previous = list(pedal.params[:AMP_KNOBS])
        pedal.id = new
        self._mark_edited()
        if not self.keep_knobs or len(previous) < AMP_KNOBS:
            return
        LOG.info("Amp changed on the amp from %s to %s; keeping the amp knobs", old, new)
        for index, value in enumerate(previous):
            self.spark.set_param(new, index, value)

    def _mark_edited(self) -> None:
        if self.state is not None and not self.state.edited:
            self.state.edited = True
            GLib.idle_add(self._on_result, "edited")

    # Commands

    def _cmd_refresh(self) -> None:
        self._refresh_requested = True

    def _cmd_select_preset(self, number: int) -> None:
        self._dry_states = None
        if not self.spark.select_preset(number):
            GLib.idle_add(self._on_error, f"The amp didn't switch to preset {number + 1}.")
        if self.state is not None:
            self.state.edited = False
        self._refresh_requested = True

    def _cmd_toggle(self, effect: str, on: bool) -> None:
        if not self.spark.set_enabled(effect, on):
            GLib.idle_add(self._on_error, "The amp didn't acknowledge the switch.")
        self._track_toggle(effect, on)
        self._mark_edited()

    def _cmd_change_model(self, slot: str, old: str, new: str, keep_knobs: bool) -> None:
        self._flush_params()
        pedal = self._pedal(old)
        previous = list(pedal.params) if pedal else []
        try:
            ok = self.spark.change_model(old, new)
        except UnsupportedModel as err:
            GLib.idle_add(self._on_error, str(err))
            self._refresh_requested = True
            return
        if not ok:
            GLib.idle_add(self._on_error, f"The amp didn't accept {catalog.display_name(new)}.")
        else:
            model = catalog.model(new)
            values = [p.default for p in model.params] if model else []
            if keep_knobs and slot == "amp":
                values[:AMP_KNOBS] = previous[:AMP_KNOBS]
            for index, value in enumerate(values):
                self.spark.set_param(new, index, value)
            self._mark_edited()
        self._refresh_requested = True

    def _cmd_load_preset(self, preset: Preset, name: str) -> None:
        self._dry_states = None
        try:
            ok = self.spark.load_preset(preset)
        except UnsupportedModel as err:
            GLib.idle_add(self._on_result, "failed", name, str(err))
            return
        except Exception as err:
            GLib.idle_add(self._on_result, "failed", name, str(err))
            raise
        if self.state is not None:
            self.state.edited = True
        self._refresh_requested = True
        GLib.idle_add(self._on_result, "loaded" if ok else "failed", name,
                      None if ok else "The amp didn't accept the preset.")

    def _cmd_save_file(self, path: Path, name: str) -> None:
        preset = self.spark.get_current()
        preset.name = name
        preset.save(path)
        LOG.info("Saved %r to %s", name, path)
        GLib.idle_add(self._on_result, "saved", str(path))

    def _cmd_backup(self, folder: Path) -> None:
        folder = folder / datetime.now().strftime("%Y-%m-%d %H%M%S")
        folder.mkdir(parents=True, exist_ok=True)
        for n in range(4):
            preset = self.spark.get_preset(n)
            preset.save(folder / f"{n + 1} - {preset.name.replace('/', '-')}.json")
        LOG.info("Backed up the four presets to %s", folder)
        GLib.idle_add(self._on_result, "backup", str(folder))

    def _cmd_dry(self, on: bool) -> None:
        """Switch every block off so the USB recording carries the dry guitar, or switch them back."""
        if self.state is None:
            return
        pedals = self.state.current.pedals
        if on and self._dry_states is None:
            self._dry_states = [p.on for p in pedals]
            for pedal in pedals:
                if pedal.on:
                    self.spark.set_enabled(pedal.id, False)
                    pedal.on = False
        elif not on and self._dry_states is not None:
            for pedal, was_on in zip(pedals, self._dry_states):
                if was_on and not pedal.on:
                    self.spark.set_enabled(pedal.id, True)
                    pedal.on = True
            self._dry_states = None
        self.state.dry = self._dry_states is not None
        GLib.idle_add(self._on_state, copy.deepcopy(self.state))
