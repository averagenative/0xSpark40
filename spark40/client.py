"""High-level control of a Spark 40: queries, changes, presets, and the amp's change reports.

Replies and acknowledgements carry the sequence number of the request they answer. Anything
else that arrives, such as a knob turned on the amp, is queued as an Event for ``listen()``.
"""

from __future__ import annotations

import collections
import time
from dataclasses import dataclass
from typing import Callable, Iterator

from . import catalog, log
from . import protocol as p
from .preset import Preset

LOG = log.get("client")

REPLY_TIMEOUT = 2.0
PRESET_TIMEOUT = 4.0


class SparkError(RuntimeError):
    pass


class UnsupportedModel(SparkError):
    pass


@dataclass
class Event:
    """A change reported by the amp.

    kind is one of: "param" (effect, index, value), "model" (old, new), "toggle" (effect, on),
    "preset" (preset: 0-3 selected on the amp), "stored" (preset: 0-3 saved on the amp),
    "tempo" (value), "level" (value), or "other" (message).
    """
    kind: str
    effect: str = ""
    index: int = 0
    value: float = 0.0
    on: bool = False
    old: str = ""
    new: str = ""
    preset: int = 0
    message: p.Message | None = None


def parse_event(message: p.Message) -> Event:
    r = message.reader()
    try:
        if message.key == (p.REPLY, p.PARAM_CHANGED):
            return Event("param", effect=r.string(), index=r.int(), value=r.float(), message=message)
        if message.key == (p.REPLY, p.MODEL):
            return Event("model", old=r.string(), new=r.string(), message=message)
        if message.key == (p.REPLY, p.TOGGLE):
            return Event("toggle", effect=r.string(), on=r.bool(), message=message)
        if message.key in ((p.REPLY, p.SELECT), (p.REPLY, p.STORED)):
            r.byte()
            kind = "preset" if message.sub == p.SELECT else "stored"
            return Event(kind, preset=r.byte(), message=message)
        if message.key == (p.REPLY, p.TAP_TEMPO):
            return Event("tempo", value=r.float(), message=message)
        if message.key == (p.REPLY, p.AMP_INFO):
            return Event("level", value=r.float(), message=message)
    except p.ProtocolError as err:
        LOG.warning("Couldn't read %r: %s", message, err)
    return Event("other", message=message)


class Spark:
    def __init__(self, transport):
        self.transport = transport
        self._seq = p.FIRST_SEQ
        self._events: collections.deque[Event] = collections.deque()
        self.firmware: tuple[int, int, int, int] | None = None

    @classmethod
    def open(cls, address: str | None = None) -> Spark:
        from .ble import SparkBle
        spark = cls(SparkBle(address))
        try:
            spark.firmware = spark.get_firmware()
        except SparkError as err:
            LOG.warning("Couldn't read the firmware version: %s", err)
        return spark

    def close(self) -> None:
        self.transport.close()

    def __enter__(self) -> Spark:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # Plumbing

    def _send(self, cmd: int, sub: int, payload: bytes = b"") -> list[bytes]:
        blocks = p.encode(cmd, sub, payload, self._seq)
        self._seq = p.next_seq(self._seq, len(blocks))
        return blocks

    def _wait(self, match: Callable[[p.Message], bool], timeout: float) -> p.Message | None:
        deadline = time.monotonic() + timeout
        while (left := deadline - time.monotonic()) > 0:
            message = self.transport.receive(timeout=left)
            if message is None:
                break
            if match(message):
                return message
            self._unsolicited(message)
        return None

    def _unsolicited(self, message: p.Message) -> None:
        if message.cmd in (p.ACK, p.ACK_LAST):
            LOG.debug("Unmatched acknowledgement %r", message)
            return
        self._events.append(parse_event(message))

    def query(self, sub: int, payload: bytes = b"", timeout: float = REPLY_TIMEOUT) -> p.Message:
        blocks = self._send(p.GET, sub, payload)
        seq = p.block_seq(blocks[0])
        for block in blocks:
            self.transport.write(block)
        reply = self._wait(lambda m: m.key == (p.REPLY, sub) and m.seq == seq, timeout)
        if reply is None:
            raise SparkError(f"No reply from the amp to request 02 {sub:02x}")
        return reply

    def command(self, sub: int, payload: bytes = b"", ack: bool = True, timeout: float = REPLY_TIMEOUT) -> bool:
        """Send a change. Returns whether the amp acknowledged every block of it."""
        for block in self._send(p.SET, sub, payload):
            seq = p.block_seq(block)
            self.transport.write(block)
            if ack and self._wait(lambda m: m.cmd in (p.ACK, p.ACK_LAST) and m.sub == sub and m.seq == seq,
                                  timeout) is None:
                LOG.warning("The amp didn't acknowledge 01 %02x (seq %d)", sub, seq)
                return False
        return True

    # Queries

    def get_name(self) -> str:
        return self.query(p.NAME).reader().string()

    def get_serial(self) -> str:
        return "".join(c for c in self.query(p.SERIAL).reader().string() if c.isascii() and c.isprintable())

    def get_firmware(self) -> tuple[int, int, int, int]:
        return p.firmware_tuple(self.query(p.FIRMWARE).reader().int())

    def get_active_preset(self) -> int:
        """The hardware preset (0-3) the amp is on. Edits made since don't change it."""
        r = self.query(p.ACTIVE).reader()
        r.byte()
        return r.byte()

    def get_preset(self, number: int) -> Preset:
        """A stored hardware preset, 0-3."""
        return Preset.parse(self.query(p.PRESET, bytes((0x00, number)) + bytes(35), PRESET_TIMEOUT).payload)

    def get_current(self) -> Preset:
        """The settings the amp is playing right now, including unsaved changes."""
        return Preset.parse(self.query(p.PRESET, bytes((0x01, 0x00)) + bytes(35), PRESET_TIMEOUT).payload)

    # Changes

    def select_preset(self, number: int) -> bool:
        return self.command(p.SELECT, bytes((0x00, number)))

    def set_param(self, effect: str, index: int, value: float) -> None:
        """Set one knob, 0.0 to 1.0. The amp doesn't acknowledge these."""
        payload = p.Writer().prefixed_string(effect).int(index).float(min(1.0, max(0.0, value))).bytes()
        self.command(p.PARAM, payload, ack=False)

    def set_enabled(self, effect: str, on: bool) -> bool:
        return self.command(p.TOGGLE, p.Writer().prefixed_string(effect).bool(on).bytes())

    def check_supported(self, model_id: str) -> None:
        model = catalog.model(model_id)
        if model is None:
            raise UnsupportedModel(f"{model_id!r} isn't a known Spark 40 model")
        if not model.supported_by(self.firmware):
            fw = p.firmware_text(self.firmware) if self.firmware else "unknown"
            raise UnsupportedModel(f"{model.name} ({model_id}) needs newer firmware than this amp's {fw}; "
                                   "loading it can crash the amp")

    def change_model(self, old: str, new: str, force: bool = False) -> bool:
        if not force:
            self.check_supported(new)
        return self.command(p.MODEL, p.Writer().prefixed_string(old).prefixed_string(new).bytes())

    def load_preset(self, preset: Preset, force: bool = False) -> bool:
        """Send a preset to the amp's live slot and switch to it. Stored presets stay as they are."""
        bad = preset.unsupported(self.firmware)
        if bad and not force:
            raise UnsupportedModel(f"This firmware lacks {', '.join(bad)}; loading the preset can crash the amp")
        if not self.command(p.PRESET, preset.encode(slot=p.TEMP_SLOT), timeout=PRESET_TIMEOUT):
            return False
        return self.select_preset(p.TEMP_SLOT)

    # Change reports

    def listen(self, timeout: float | None = None) -> Iterator[Event]:
        """Yield the amp's change reports. With a timeout, stop after that long without one."""
        while True:
            while self._events:
                yield self._events.popleft()
            message = self.transport.receive(timeout=timeout if timeout is not None else 0.5)
            if message is None:
                if timeout is not None:
                    return
                if not self.transport.alive():
                    raise SparkError("Lost the connection to the amp")
                continue
            self._unsolicited(message)

    def poll(self, timeout: float = 0.05) -> list[Event]:
        """The change reports that arrive within ``timeout`` seconds, without blocking longer."""
        deadline = time.monotonic() + timeout
        while (left := deadline - time.monotonic()) > 0:
            message = self.transport.receive(timeout=left)
            if message is None:
                break
            self._unsolicited(message)
        return self.pending_events()

    def pending_events(self) -> list[Event]:
        events = list(self._events)
        self._events.clear()
        return events
