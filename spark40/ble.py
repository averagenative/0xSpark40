"""Bluetooth LE transport for the Spark 40, through BlueZ over D-Bus.

The amp advertises as "Spark 40 BLE" and needs no pairing. It has one GATT service (0xFFC0)
with a write characteristic (0xFFC1) and a notify characteristic (0xFFC2). Blocks go out with
WriteValue; AcquireNotify hands back a socket for the notifications, so reading needs a reader
thread and no GLib main loop. Only one client can be connected at a time, so the Spark app on a
phone has to be closed first.
"""

from __future__ import annotations

import os
import queue
import select
import threading
import time

from gi.repository import Gio, GLib

from . import log
from .protocol import Decoder, Message

LOG = log.get("ble")

BLUEZ = "org.bluez"
SERVICE = "0000ffc0-0000-1000-8000-00805f9b34fb"
WRITE_CHAR = "0000ffc1-0000-1000-8000-00805f9b34fb"
NOTIFY_CHAR = "0000ffc2-0000-1000-8000-00805f9b34fb"
DEFAULT_MTU = 23
WRITE_PIECE = 100


class SparkNotFound(RuntimeError):
    pass


def _bus() -> Gio.DBusConnection:
    return Gio.bus_get_sync(Gio.BusType.SYSTEM, None)


def _objects(bus) -> dict:
    reply = bus.call_sync(BLUEZ, "/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects",
                          None, None, Gio.DBusCallFlags.NONE, 5000, None)
    return reply.unpack()[0]


def _get(bus, path: str, iface: str, name: str):
    reply = bus.call_sync(BLUEZ, path, "org.freedesktop.DBus.Properties", "Get",
                          GLib.Variant("(ss)", (iface, name)), None, Gio.DBusCallFlags.NONE, 2000, None)
    return reply.unpack()[0]


def _is_spark(dev: dict, address: str | None) -> bool:
    if address:
        return str(dev.get("Address", "")).upper() == address.upper()
    name = str(dev.get("Name") or dev.get("Alias") or "")
    uuids = [u.lower() for u in dev.get("UUIDs", [])]
    return "spark" in name.lower() and ("ble" in name.lower() or SERVICE in uuids)


def find_spark(address: str | None = None, bus=None) -> dict | None:
    """A Spark BlueZ already knows about: paths, name, address, and whether it's connected."""
    try:
        bus = bus or _bus()
        objects = _objects(bus)
    except GLib.Error:
        return None
    found = []
    for path, ifaces in objects.items():
        dev = ifaces.get("org.bluez.Device1")
        if dev and _is_spark(dev, address):
            found.append({"device": path, "adapter": dev.get("Adapter"), "name": dev.get("Name") or dev.get("Alias"),
                          "address": dev.get("Address"), "connected": bool(dev.get("Connected"))})
    found.sort(key=lambda d: not d["connected"])
    return found[0] if found else None


def _adapter(bus) -> str | None:
    for path, ifaces in _objects(bus).items():
        if "org.bluez.Adapter1" in ifaces and ifaces["org.bluez.Adapter1"].get("Powered"):
            return path
    return None


def discover(address: str | None = None, timeout: float = 20.0) -> dict | None:
    """Scan for a Spark over Bluetooth LE. BlueZ forgets unpaired devices soon after a scan ends."""
    bus = _bus()
    info = find_spark(address, bus)
    if info:
        return info
    adapter = _adapter(bus)
    if adapter is None:
        raise SparkNotFound("No powered Bluetooth adapter found.")
    LOG.info("Scanning for the Spark over Bluetooth...")
    call = lambda method, args=None: bus.call_sync(BLUEZ, adapter, "org.bluez.Adapter1", method, args, None,
                                                   Gio.DBusCallFlags.NONE, 5000, None)
    try:
        call("SetDiscoveryFilter", GLib.Variant("(a{sv})", ({"Transport": GLib.Variant("s", "le")},)))
    except GLib.Error as err:
        LOG.debug("SetDiscoveryFilter: %s", err.message)
    started = False
    try:
        call("StartDiscovery")
        started = True
    except GLib.Error as err:
        LOG.debug("StartDiscovery: %s (another scan may be running)", err.message)
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            info = find_spark(address, bus)
            if info:
                return info
            time.sleep(0.5)
        return None
    finally:
        if started:
            try:
                call("StopDiscovery")
            except GLib.Error:
                pass


class SparkBle:
    """write(block), receive(timeout) -> Message, alive(), close()."""

    kind = "Bluetooth"

    def __init__(self, address: str | None = None, connect_timeout: float = 20.0, scan_timeout: float = 20.0):
        info = discover(address, scan_timeout)
        if info is None:
            raise SparkNotFound("No Spark found over Bluetooth. Turn the amp on, and close the Spark app on "
                                "any phone or tablet that might be connected to it.")
        self.bus = _bus()
        self.device = info["device"]
        self.name = info.get("name") or "Spark"
        self.address = info.get("address")
        self.path = f"bluetooth:{self.address}"
        if not info.get("connected"):
            self._connect(connect_timeout)
        self.write_char, self.notify_char = self._characteristics(connect_timeout)
        reply, fds = self.bus.call_with_unix_fd_list_sync(
            BLUEZ, self.notify_char, "org.bluez.GattCharacteristic1", "AcquireNotify",
            GLib.Variant("(a{sv})", ({},)), GLib.VariantType.new("(hq)"), Gio.DBusCallFlags.NONE, 5000, None, None)
        handle, self.mtu = reply.unpack()
        self.notify_fd = fds.get(handle)
        LOG.debug("Notify MTU %d", self.mtu)
        self.messages: queue.Queue[Message] = queue.Queue()
        self._stop = threading.Event()
        self._reader = threading.Thread(target=self._read_loop, name="spark40-ble-in", daemon=True)
        self._reader.start()

    def _connect(self, timeout: float) -> None:
        LOG.info("Connecting to %s (%s)", self.name, self.address)
        try:
            self.bus.call_sync(BLUEZ, self.device, "org.bluez.Device1", "Connect", None, None,
                               Gio.DBusCallFlags.NONE, int(timeout * 1000), None)
            return
        except GLib.Error as err:
            if "InProgress" not in err.message and "AlreadyConnected" not in err.message:
                raise SparkNotFound("Couldn't connect to the Spark over Bluetooth. Turn the amp on, and close the "
                                    f"Spark app on any phone or tablet connected to it. ({err.message})") from err
        # Another connect attempt is already running; wait for it instead of failing.
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if _get(self.bus, self.device, "org.bluez.Device1", "Connected"):
                    return
            except GLib.Error:
                break
            time.sleep(0.25)
        raise SparkNotFound("Couldn't connect to the Spark over Bluetooth. Turn the amp on and try again.")

    def _characteristics(self, timeout: float) -> tuple[str, str]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            chars = {}
            for path, ifaces in _objects(self.bus).items():
                char = ifaces.get("org.bluez.GattCharacteristic1")
                if char and path.startswith(self.device + "/"):
                    chars[char.get("UUID")] = path
            if WRITE_CHAR in chars and NOTIFY_CHAR in chars:
                return chars[WRITE_CHAR], chars[NOTIFY_CHAR]
            time.sleep(0.25)
        raise SparkNotFound("Connected to the Spark, but its control service didn't appear.")

    def write(self, block: bytes) -> None:
        log.frame("TX", block, "ble")
        # The amp rejects long writes ("Invalid Length"), so send pieces of at most WRITE_PIECE bytes;
        # it reassembles blocks from the length in their header.
        room = min(max(self.mtu - 3, DEFAULT_MTU - 3), WRITE_PIECE)
        for i in range(0, len(block), room):
            self.bus.call_sync(BLUEZ, self.write_char, "org.bluez.GattCharacteristic1", "WriteValue",
                               GLib.Variant("(aya{sv})", (block[i:i + room], {"type": GLib.Variant("s", "request")})),
                               None, Gio.DBusCallFlags.NONE, 5000, None)

    def receive(self, timeout: float | None = None) -> Message | None:
        try:
            return self.messages.get(timeout=timeout)
        except queue.Empty:
            return None

    def _read_loop(self) -> None:
        decoder = Decoder()
        while not self._stop.is_set():
            ready, _, _ = select.select([self.notify_fd], [], [], 0.1)
            if not ready:
                continue
            try:
                data = os.read(self.notify_fd, 1024)
            except OSError as err:
                LOG.warning("Bluetooth notifications stopped: %s", err)
                break
            if not data:
                LOG.warning("Bluetooth notification socket closed; the link probably dropped")
                break
            log.frame("RX", data, "ble")
            for message in decoder.feed(data):
                self.messages.put(message)

    def alive(self) -> bool:
        if not self._reader.is_alive():
            return False
        try:
            return bool(_get(self.bus, self.device, "org.bluez.Device1", "Connected"))
        except GLib.Error:
            return False

    def close(self, disconnect: bool = True) -> None:
        self._stop.set()
        self._reader.join(timeout=1)
        try:
            os.close(self.notify_fd)
        except OSError:
            pass
        if disconnect:
            try:
                self.bus.call_sync(BLUEZ, self.device, "org.bluez.Device1", "Disconnect", None, None,
                                   Gio.DBusCallFlags.NONE, 5000, None)
            except GLib.Error:
                pass

    def __enter__(self) -> SparkBle:
        return self

    def __exit__(self, *exc) -> None:
        self.close()
