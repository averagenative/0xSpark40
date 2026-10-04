"""Spark presets: the amp's binary form and the JSON form other Spark tools use.

A preset is a name and metadata plus seven pedals in fixed order (gate, compressor, drive,
amp, modulation, delay, reverb), each with an on/off state and a list of 0.0 to 1.0 values.
The last byte of the binary form is a checksum: the sum of every byte after the two-byte
slot header, modulo 256.

The JSON form matches Ignitron and Paul Hamshere's tools: ``Name``, ``UUID``, ``Pedals`` with
``Name``, ``IsOn`` (or ``OnOff``: "On"/"Off"), and ``Parameters``.
"""

from __future__ import annotations

import json
import uuid as uuidlib
from dataclasses import dataclass, field
from pathlib import Path

from . import catalog
from .protocol import ProtocolError, Reader, TEMP_SLOT, Writer


def ascii_text(text: str) -> str:
    """Text the amp can store: printable ASCII, with anything else (accents, emoji) dropped."""
    kept = "".join(c for c in text if " " <= c <= "~")
    return " ".join(kept.split())


@dataclass
class Pedal:
    id: str
    on: bool
    params: list[float]

    @property
    def name(self) -> str:
        return catalog.display_name(self.id, self.params)


@dataclass
class Preset:
    name: str
    pedals: list[Pedal]
    uuid: str = field(default_factory=lambda: str(uuidlib.uuid4()).upper())
    version: str = "0.7"
    description: str = ""
    icon: str = "icon.png"
    bpm: float = 120.0
    slot: int = TEMP_SLOT
    current: int = 0
    checksum: int | None = None

    def pedal(self, slot: str) -> Pedal:
        return self.pedals[catalog.SLOTS.index(slot)]

    @classmethod
    def parse(cls, payload: bytes) -> Preset:
        r = Reader(payload)
        current, slot = r.byte(), r.byte()
        uuid, name, version, description, icon = (r.string() for _ in range(5))
        bpm = r.float()
        pedals = []
        for _ in range(r.array()):
            pedal_id, on = r.string(), r.bool()
            values = []
            for _ in range(r.array()):
                r.int()          # parameter index; always 0, 1, 2, ...
                if r.array() != 1:
                    raise ProtocolError("expected a one-element array around each parameter value")
                values.append(r.float())
            pedals.append(Pedal(pedal_id, on, values))
        checksum = r.byte() if r.remaining() else None
        return cls(name=name, pedals=pedals, uuid=uuid, version=version, description=description,
                   icon=icon, bpm=bpm, slot=slot, current=current, checksum=checksum)

    def encode(self, slot: int | None = None) -> bytes:
        """The payload for sending this preset to ``slot`` (0-3, or the live slot 0x7F)."""
        w = Writer().long_string(ascii_text(self.uuid)).string(ascii_text(self.name)).string(ascii_text(self.version))
        w.string(ascii_text(self.description)[:255]).string(ascii_text(self.icon)).float(self.bpm)
        w.array(len(self.pedals))
        for pedal in self.pedals:
            w.string(pedal.id).bool(pedal.on).array(len(pedal.params))
            for index, value in enumerate(pedal.params):
                w.int(index).array(1).float(value)
        body = w.bytes()
        return bytes((0x00, self.slot if slot is None else slot)) + body + bytes((sum(body) & 0xFF,))

    def unsupported(self, firmware: tuple[int, ...] | None) -> list[str]:
        """Pedals whose model this firmware lacks (sending them can crash the amp)."""
        bad = []
        for pedal in self.pedals:
            model = catalog.model(pedal.id)
            if model is None or not model.supported_by(firmware):
                bad.append(pedal.id)
        return bad

    def to_dict(self) -> dict:
        return {
            "PresetNumber": self.slot, "UUID": self.uuid, "Name": self.name, "Version": self.version,
            "Description": self.description, "Icon": self.icon, "BPM": self.bpm,
            "Pedals": [{"Name": p.id, "IsOn": p.on, "Parameters": [round(v, 4) for v in p.params]}
                       for p in self.pedals],
            "Filler": self.encode()[-1],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Preset:
        pedals = []
        for p in data["Pedals"]:
            on = p["IsOn"] if "IsOn" in p else str(p.get("OnOff", "On")).lower() == "on"
            values = [float(v["Value"] if isinstance(v, dict) else v) for v in p["Parameters"]]
            pedals.append(Pedal(p["Name"], bool(on), values))
        if len(pedals) != len(catalog.SLOTS):
            raise ValueError(f"a preset needs {len(catalog.SLOTS)} pedals, this one has {len(pedals)}")
        return cls(name=data.get("Name", "Untitled"), pedals=pedals,
                   uuid=data.get("UUID") or str(uuidlib.uuid4()).upper(),
                   version=data.get("Version", "0.7"), description=data.get("Description", ""),
                   icon=data.get("Icon", "icon.png"), bpm=float(data.get("BPM", 120.0)))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2) + "\n")

    @classmethod
    def load(cls, path: str | Path) -> Preset:
        return cls.from_dict(json.loads(Path(path).read_text()))
