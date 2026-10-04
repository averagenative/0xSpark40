"""Spark 40 message framing: blocks, chunks, 7-bit packing, and the amp's msgpack-like values.

A message is a command byte, a sub-command byte, and a payload. On the wire the payload is
packed to 7-bit bytes and wrapped in a chunk (``F0 01 seq checksum cmd sub ... F7``); chunks
travel inside blocks that start with a 16-byte header. Presets are long enough to span several
chunks, each carrying a small sub-header. See docs/protocol.md.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from . import log

LOG = log.get("protocol")

MAGIC = b"\x01\xfe\x00\x00"
TO_AMP = b"\x53\xfe"
FROM_AMP = b"\x41\xff"
HEADER_LEN = 16

# Messages that carry a preset span chunks; each chunk's data starts with
# [chunk count, chunk index, data length].
MULTI_CHUNK = {(0x01, 0x01), (0x03, 0x01)}
SEND_CHUNK_DATA = 0x80   # preset bytes per chunk sent to the amp (one chunk per 0xad-byte block)

# Commands
SET = 0x01          # app -> amp: change something
GET = 0x02          # app -> amp: ask for something
REPLY = 0x03        # amp -> app: an answer, or a change made on the amp
ACK = 0x04          # amp -> app: command received
ACK_LAST = 0x05     # amp -> app: final preset chunk received

# Sub-commands
PRESET = 0x01
PARAM = 0x04
MODEL = 0x06
ACTIVE = 0x10
NAME = 0x11
TOGGLE = 0x15
SERIAL = 0x23
STORED = 0x27
AMP_INFO = 0x28
CHECKSUMS = 0x2A
FIRMWARE = 0x2F
PARAM_CHANGED = 0x37
SELECT = 0x38
TAP_TEMPO = 0x63

TEMP_SLOT = 0x7F    # the live "software" preset the app sends edits to


class ProtocolError(ValueError):
    pass


def pack7(data: bytes) -> bytes:
    """Pack 8-bit bytes for the wire: each group of up to 7 bytes is preceded by their top bits."""
    out = bytearray()
    for i in range(0, len(data), 7):
        group = data[i:i + 7]
        out.append(sum(1 << j for j, b in enumerate(group) if b & 0x80))
        out.extend(b & 0x7F for b in group)
    return bytes(out)


def unpack7(data: bytes) -> bytes:
    out = bytearray()
    for i in range(0, len(data), 8):
        top, group = data[i], data[i + 1:i + 8]
        out.extend(b | (0x80 if top & (1 << j) else 0) for j, b in enumerate(group))
    return bytes(out)


def checksum(packed: bytes) -> int:
    value = 0
    for b in packed:
        value ^= b
    return value


@dataclass
class Message:
    cmd: int
    sub: int
    payload: bytes = b""
    seq: int = 0

    @property
    def key(self) -> tuple[int, int]:
        return self.cmd, self.sub

    def reader(self) -> Reader:
        return Reader(self.payload)

    def __repr__(self) -> str:
        return f"Message({self.cmd:02x} {self.sub:02x} seq={self.seq} {self.payload.hex(' ')})"


def _chunk(seq: int, cmd: int, sub: int, data: bytes) -> bytes:
    packed = pack7(data)
    return bytes((0xF0, 0x01, seq, checksum(packed), cmd, sub)) + packed + b"\xf7"


def _block(content: bytes, direction: bytes = TO_AMP) -> bytes:
    return MAGIC + direction + bytes((HEADER_LEN + len(content), 0)) + bytes(8) + content


# Sequence numbers from the app run 0x01 to 0x3E; the amp numbers its own messages from 0x40.
FIRST_SEQ = 0x01
LAST_SEQ = 0x3E


def next_seq(seq: int, steps: int = 1) -> int:
    for _ in range(steps):
        seq = FIRST_SEQ if seq >= LAST_SEQ else seq + 1
    return seq


def block_seq(block: bytes) -> int:
    """The sequence number of the (first) chunk in a block."""
    return block[HEADER_LEN + 2]


def encode(cmd: int, sub: int, payload: bytes = b"", seq: int = FIRST_SEQ) -> list[bytes]:
    """Frame one message as the blocks to write to the amp, in order.

    Each chunk of a multi-chunk preset takes the next sequence number, as the Spark app does;
    the amp acknowledges each chunk under its own number.
    """
    if (cmd, sub) not in MULTI_CHUNK:
        return [_block(_chunk(seq, cmd, sub, payload))]
    parts = [payload[i:i + SEND_CHUNK_DATA] for i in range(0, len(payload), SEND_CHUNK_DATA)] or [b""]
    return [_block(_chunk(next_seq(seq, i), cmd, sub, bytes((len(parts), i, len(part))) + part))
            for i, part in enumerate(parts)]


class Decoder:
    """Turns the amp's notification bytes back into Messages.

    Blocks can arrive split across notifications, chunks can span blocks, and a preset spans
    many chunks, so everything is buffered until complete.
    """

    def __init__(self):
        self._blocks = bytearray()
        self._chunks = bytearray()
        self._parts: dict[tuple[int, int], list[bytes]] = {}

    def feed(self, data: bytes) -> list[Message]:
        self._blocks.extend(data)
        messages = []
        while True:
            start = self._blocks.find(MAGIC)
            if start < 0:
                del self._blocks[:max(0, len(self._blocks) - len(MAGIC) + 1)]
                break
            if start:
                LOG.debug("Skipping %d stray bytes before a block", start)
                del self._blocks[:start]
            if len(self._blocks) < 7:
                break
            size = self._blocks[6]
            if size < HEADER_LEN:
                del self._blocks[:len(MAGIC)]
                continue
            if len(self._blocks) < size:
                break
            self._chunks.extend(self._blocks[HEADER_LEN:size])
            del self._blocks[:size]
            messages.extend(self._drain_chunks())
        return messages

    def _drain_chunks(self) -> list[Message]:
        messages = []
        while True:
            start = self._chunks.find(b"\xf0\x01")
            if start < 0:
                self._chunks.clear()
                break
            end = self._chunks.find(b"\xf7", start)
            if end < 0:
                del self._chunks[:start]
                break
            chunk = bytes(self._chunks[start:end + 1])
            del self._chunks[:end + 1]
            message = self._chunk(chunk)
            if message is not None:
                messages.append(message)
        return messages

    def _chunk(self, chunk: bytes) -> Message | None:
        if len(chunk) < 7:
            return None
        seq, chk, cmd, sub, packed = chunk[2], chunk[3], chunk[4], chunk[5], chunk[6:-1]
        if checksum(packed) != chk:
            LOG.warning("Checksum mismatch in %02x %02x (seq %d); keeping the data", cmd, sub, seq)
        data = unpack7(packed)
        if (cmd, sub) not in MULTI_CHUNK or len(data) < 3:
            return Message(cmd, sub, data, seq)
        count, index, length = data[0], data[1], data[2]
        key = (cmd, sub)       # the amp repeats one sequence number across chunks; the app counts up
        parts = self._parts.setdefault(key, [])
        if index != len(parts):
            LOG.warning("Preset chunk %d arrived when %d was expected; dropping the partial preset", index, len(parts))
            self._parts.pop(key, None)
            return None
        parts.append(data[3:3 + length])
        if index + 1 < count:
            return None
        del self._parts[key]
        return Message(cmd, sub, b"".join(parts), seq)


class Reader:
    """Reads the amp's msgpack-like values from a payload."""

    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def remaining(self) -> int:
        return len(self.data) - self.pos

    def byte(self) -> int:
        if self.pos >= len(self.data):
            raise ProtocolError("payload ended early")
        value = self.data[self.pos]
        self.pos += 1
        return value

    def take(self, n: int) -> bytes:
        if self.pos + n > len(self.data):
            raise ProtocolError("payload ended early")
        value = self.data[self.pos:self.pos + n]
        self.pos += n
        return value

    def int(self) -> int:
        first = self.byte()
        if first < 0x80:
            return first
        sizes = {0xCC: 1, 0xCD: 2, 0xCE: 4, 0xCF: 8}
        if first not in sizes:
            raise ProtocolError(f"expected an integer, got 0x{first:02x}")
        return int.from_bytes(self.take(sizes[first]), "big")

    def string(self) -> str:
        first = self.byte()
        if first == 0xD9:
            length = self.byte()
        elif 0xA0 <= first <= 0xBF:
            length = first - 0xA0
        elif first < 0x20:
            # The amp's "prefixed" string: a length byte, then a normal short string.
            second = self.byte()
            if not 0xA0 <= second <= 0xBF:
                raise ProtocolError(f"bad prefixed string header {first:02x} {second:02x}")
            length = second - 0xA0
        else:
            raise ProtocolError(f"expected a string, got 0x{first:02x}")
        return self.take(length).decode("latin-1")

    def float(self) -> float:
        first = self.byte()
        if first != 0xCA:
            raise ProtocolError(f"expected a float, got 0x{first:02x}")
        return struct.unpack(">f", self.take(4))[0]

    def bool(self) -> bool:
        first = self.byte()
        if first not in (0xC2, 0xC3):
            raise ProtocolError(f"expected a boolean, got 0x{first:02x}")
        return first == 0xC3

    def array(self) -> int:
        first = self.byte()
        if not 0x90 <= first <= 0x9F:
            raise ProtocolError(f"expected an array, got 0x{first:02x}")
        return first - 0x90


class Writer:
    """Builds a payload from the amp's msgpack-like values."""

    def __init__(self):
        self.data = bytearray()

    def raw(self, *values: int) -> Writer:
        self.data.extend(values)
        return self

    def int(self, value: int) -> Writer:
        if value < 0x80:
            self.data.append(value)
        elif value < 0x100:
            self.data.extend((0xCC, value))
        else:
            self.data.append(0xCE)
            self.data.extend(value.to_bytes(4, "big"))
        return self

    def string(self, text: str) -> Writer:
        raw = text.encode("latin-1")
        if len(raw) < 32:
            self.data.append(0xA0 + len(raw))
        else:
            self.data.extend((0xD9, len(raw)))
        self.data.extend(raw)
        return self

    def long_string(self, text: str) -> Writer:
        raw = text.encode("latin-1")
        self.data.extend((0xD9, len(raw)))
        self.data.extend(raw)
        return self

    def prefixed_string(self, text: str) -> Writer:
        raw = text.encode("latin-1")
        if len(raw) >= 32:
            raise ProtocolError(f"name too long for the amp: {text!r}")
        self.data.extend((len(raw), 0xA0 + len(raw)))
        self.data.extend(raw)
        return self

    def float(self, value: float) -> Writer:
        self.data.append(0xCA)
        self.data.extend(struct.pack(">f", value))
        return self

    def bool(self, value: bool) -> Writer:
        self.data.append(0xC3 if value else 0xC2)
        return self

    def array(self, count: int) -> Writer:
        self.data.append(0x90 + count)
        return self

    def bytes(self) -> bytes:
        return bytes(self.data)


def firmware_tuple(value: int) -> tuple[int, int, int, int]:
    return tuple(value.to_bytes(4, "big"))  # type: ignore[return-value]


def firmware_text(version: tuple[int, ...]) -> str:
    return ".".join(str(v) for v in version)
