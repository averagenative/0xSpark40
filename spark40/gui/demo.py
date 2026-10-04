"""Demo mode: the full window with sample settings and no amp, for screenshots and testing."""

from __future__ import annotations

from ..preset import Pedal, Preset
from .worker import SparkState


class DemoWorker:
    """Stands in for SparkWorker: accepts commands and does nothing."""

    def __init__(self, on_state, on_event, on_status, on_error, on_result=None):
        self.on_state, self.on_status = on_state, on_status

    def start(self) -> None:
        from gi.repository import GLib

        GLib.idle_add(lambda: (self.on_status(True, "Bluetooth"), self.on_state(sample_state()), False)[-1])

    def stop(self) -> None:
        pass

    def retry(self) -> None:
        pass

    def set_param(self, *args) -> None:
        pass

    def submit(self, *args) -> None:
        pass


def sample_state() -> SparkState:
    pedals = [
        Pedal("bias.noisegate", True, [0.12, 0.33, 0.0]),
        Pedal("Compressor", True, [0.33, 0.99]),
        Pedal("DistortionTS9", False, [0.13, 0.26, 0.48]),
        Pedal("Plexi", True, [0.70, 0.62, 0.43, 0.35, 0.45]),
        Pedal("ChorusAnalog", False, [0.38, 0.57, 0.22, 0.25]),
        Pedal("DelayMono", True, [0.16, 0.23, 0.49, 0.61, 1.0]),
        Pedal("bias.reverb", True, [0.34, 0.33, 0.44, 0.69, 0.49, 0.47, 0.3]),
    ]
    current = Preset(name="Demo tone", pedals=pedals, slot=2, current=1)
    return SparkState(name="Spark 40", serial="demo", firmware=(1, 2, 3, 37), transport="Bluetooth",
                      current=current, active=2, names=["1-Clean", "2-Crunch", "3-HighGain", "4-Metal"])
