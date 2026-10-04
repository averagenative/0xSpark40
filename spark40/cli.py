"""Command-line front end: ``python -m spark40 <command>``."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from . import catalog, library, log
from .client import Spark, SparkError, UnsupportedModel
from .preset import Preset
from .protocol import firmware_text

SLOT_ALIASES = {
    "gate": "gate", "noise": "gate", "noisegate": "gate",
    "comp": "comp", "compressor": "comp",
    "drive": "drive", "dist": "drive", "distortion": "drive", "od": "drive",
    "amp": "amp",
    "mod": "mod", "modulation": "mod", "fx": "mod",
    "delay": "delay", "echo": "delay",
    "reverb": "reverb", "verb": "reverb",
}

BACKUP_DIR = library.BACKUP_DIR


def slot_arg(text: str) -> str:
    slot = SLOT_ALIASES.get(text.lower())
    if slot is None:
        raise argparse.ArgumentTypeError(f"unknown section {text!r}; use one of {', '.join(catalog.SLOTS)}")
    return slot


def knob(value: float, switch: bool = False) -> str:
    if switch:
        return "On" if value >= 0.5 else "Off"
    return f"{value * 10:4.1f}"


def print_preset(preset: Preset) -> None:
    where = {0x7F: "live"}.get(preset.slot, f"slot {preset.slot + 1}")
    print(f"Preset  {preset.name!r} ({where}, {preset.bpm:g} BPM)")
    for slot, pedal in zip(catalog.SLOTS, preset.pedals):
        model = catalog.model(pedal.id)
        state = "on " if pedal.on else "off"
        print(f"  {catalog.SLOT_NAMES[slot]:11s} {state} {pedal.name}" + ("" if model else f"  ({pedal.id})"))
        for i, value in enumerate(pedal.params):
            if pedal.id == catalog.REVERB and i == catalog.REVERB_TYPE_PARAM:
                continue
            param = model.params[i] if model and i < len(model.params) else None
            name = param.name if param else f"Param {i + 1}"
            print(f"      {name:16s} {knob(value, bool(param and param.switch))}")


def cmd_info(spark: Spark, args) -> None:
    fw = firmware_text(spark.firmware) if spark.firmware else "unknown"
    print(f"Device    {spark.get_name()} over {spark.transport.kind} ({spark.transport.path})")
    print(f"Serial    {spark.get_serial()}")
    print(f"Firmware  {fw}")
    active = spark.get_active_preset()
    print("Presets:")
    for n in range(4):
        mark = "*" if n == active else " "
        print(f"  {mark}{n + 1}  {spark.get_preset(n).name}")


def cmd_dump(spark: Spark, args) -> None:
    preset = spark.get_current() if args.preset is None else spark.get_preset(args.preset - 1)
    if args.json:
        print(json.dumps(preset.to_dict(), indent=2))
    else:
        print_preset(preset)


def cmd_monitor(spark: Spark, args) -> None:
    sys.stdout.reconfigure(line_buffering=True)
    print("Listening for changes on the amp. Press Ctrl+C to stop.")
    for event in spark.listen():
        if event.kind == "param":
            print(f"{catalog.display_name(event.effect):16s} {catalog.param_name(event.effect, event.index):16s} "
                  f"{knob(event.value)}")
        elif event.kind == "preset":
            print(f"{'preset':16s} {'selected':16s} {event.preset + 1}")
        elif event.kind == "stored":
            print(f"{'preset':16s} {'saved to':16s} {event.preset + 1}")
        elif event.kind == "model":
            print(f"{'model':16s} {catalog.display_name(event.old)} -> {catalog.display_name(event.new)}")
        elif event.kind == "toggle":
            print(f"{catalog.display_name(event.effect):16s} {'on' if event.on else 'off'}")
        elif event.kind == "tempo":
            print(f"{'tap tempo':16s} {event.value:.1f} BPM")
        elif args.verbose:
            print(f"{event.kind:16s} {event.message!r}")


def cmd_preset(spark: Spark, args) -> None:
    ok = spark.select_preset(args.number - 1)
    print(f"Preset {args.number}: {spark.get_current().name}" if ok else "The amp didn't acknowledge the change.")


def find_param(model: catalog.Model | None, pedal_params: list[float], query: str) -> int:
    if query.isdigit():
        index = int(query) - 1
        if 0 <= index < len(pedal_params):
            return index
        sys.exit(f"Parameter number must be 1 to {len(pedal_params)}.")
    names = [p.name for p in model.params] if model else []
    q = query.lower().replace(" ", "")
    matches = [i for i, n in enumerate(names) if n.lower().replace(" ", "").startswith(q)]
    if len(matches) != 1:
        sys.exit(f"Unknown parameter {query!r}. Choices: {', '.join(names) or 'use a number'}")
    return matches[0]


def cmd_set(spark: Spark, args) -> None:
    pedal = spark.get_current().pedal(args.slot)
    model = catalog.model(pedal.id)
    index = find_param(model, pedal.params, args.param)
    value = args.value if args.raw else args.value / 10.0
    spark.set_param(pedal.id, index, value)
    print(f"{pedal.name} {catalog.param_name(pedal.id, index)} -> {knob(min(1.0, max(0.0, value)))}")


def cmd_toggle(spark: Spark, args) -> None:
    pedal = spark.get_current().pedal(args.slot)
    ok = spark.set_enabled(pedal.id, args.state == "on")
    print(f"{pedal.name} {args.state}" if ok else "The amp didn't acknowledge the change.")


def cmd_model(spark: Spark, args) -> None:
    matches = [m for m in catalog.find(args.name, args.slot)]
    if not matches:
        sys.exit(f"No {args.slot} model matches {args.name!r}. Run `spark40 models {args.slot}` for the list.")
    if len(matches) > 1:
        sys.exit(f"{args.name!r} matches {', '.join(m.name for m in matches)}; be more specific.")
    new = matches[0]
    pedal = spark.get_current().pedal(args.slot)
    try:
        ok = spark.change_model(pedal.id, new.id, force=args.force)
    except UnsupportedModel as err:
        sys.exit(str(err))
    print(f"{catalog.SLOT_NAMES[args.slot]}: {pedal.name} -> {new.name}" if ok else "The amp rejected the model.")


def cmd_reverb(spark: Spark, args) -> None:
    names = [t.lower().replace(" ", "") for t in catalog.REVERB_TYPES]
    q = args.type.lower().replace(" ", "")
    matches = [i for i, n in enumerate(names) if q in n]
    if len(matches) != 1:
        sys.exit(f"Reverb types: {', '.join(catalog.REVERB_TYPES)}")
    spark.set_param(catalog.REVERB, catalog.REVERB_TYPE_PARAM, matches[0] / 10)
    print(f"Reverb: {catalog.REVERB_TYPES[matches[0]]}")


def cmd_models(args) -> None:
    for slot in ([args.slot] if args.slot else catalog.SLOTS):
        print(f"{catalog.SLOT_NAMES[slot]}:")
        if slot == "reverb":
            for t in catalog.REVERB_TYPES:
                print(f"  {t}")
            continue
        for m in catalog.for_slot(slot):
            note = "" if m.since == catalog.BASE else f"  (firmware {firmware_text(m.since)} or later)"
            print(f"  {m.name:22s} {m.id}{note}")


def cmd_backup(spark: Spark, args) -> None:
    folder = Path(args.dir) if args.dir else BACKUP_DIR / datetime.now().strftime("%Y-%m-%d %H%M%S")
    folder.mkdir(parents=True, exist_ok=True)
    for n in range(4):
        preset = spark.get_preset(n)
        path = folder / f"{n + 1} - {preset.name.replace('/', '-')}.json"
        preset.save(path)
        print(f"Saved {path}")
    preset = spark.get_current()
    preset.save(folder / "current.json")
    print(f"Saved {folder / 'current.json'}")


def cmd_save(spark: Spark, args) -> None:
    preset = spark.get_current()
    if args.name:
        preset.name = args.name
    path = Path(args.file)
    preset.save(path)
    print(f"Saved {preset.name!r} to {path}")


def cmd_load(spark: Spark, args) -> None:
    preset = Preset.load(args.file)
    try:
        ok = spark.load_preset(preset, force=args.force)
    except UnsupportedModel as err:
        sys.exit(str(err))
    print(f"Loaded {preset.name!r} (not saved to a preset slot)" if ok else "The amp didn't accept the preset.")


def cmd_cloud(args) -> int:
    """Search ToneCloud, or download a preset from it. Needs no amp unless playing."""
    if args.load or args.save:
        preset = library.tonecloud_preset(args.load or args.save)
        if args.save:
            folder = library.USER_DIR / "ToneCloud"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{library.safe_name(preset.name)}.json"
            preset.save(path)
            print(f"Saved {preset.name!r} to {path}")
            return 0
        with Spark.open(args.address) as spark:
            try:
                ok = spark.load_preset(preset, force=args.force)
            except UnsupportedModel as err:
                sys.exit(str(err))
        print(f"Playing {preset.name!r} from ToneCloud" if ok else "The amp didn't accept the preset.")
        return 0
    results = library.tonecloud_search(args.keyword, order=args.order, page_size=args.count)
    for item in results:
        missing = item.missing(None)
        note = f"  (needs {', '.join(missing)})" if missing else ""
        print(f"{item.id}  {item.downloads:8,d}  {item.category:12s} {item.name}{note}")
    if not results:
        print("No presets found.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="spark40", description="Control a Positive Grid Spark 40 over Bluetooth.")
    parser.add_argument("--address", help="Bluetooth address of the amp's BLE side (default: find it)")
    parser.add_argument("--debug", action="store_true", help="log every block sent and received")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("info", help="name, serial number, firmware, and the four presets")
    p = sub.add_parser("dump", help="show the current settings, or a stored preset")
    p.add_argument("preset", nargs="?", type=int, choices=range(1, 5), help="stored preset 1-4")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("monitor", help="print changes made on the amp")
    p.add_argument("-v", "--verbose", action="store_true")
    p = sub.add_parser("preset", help="switch to stored preset 1-4")
    p.add_argument("number", type=int, choices=range(1, 5))
    p = sub.add_parser("set", help="turn a knob: spark40 set amp gain 6.5")
    p.add_argument("slot", type=slot_arg)
    p.add_argument("param", help="knob name or number")
    p.add_argument("value", type=float, help="0 to 10, like the Spark app")
    p.add_argument("--raw", action="store_true", help="value is 0.0 to 1.0")
    for state in ("on", "off"):
        p = sub.add_parser(state, help=f"switch a section {state}")
        p.add_argument("slot", type=slot_arg)
        p.set_defaults(state=state, func=cmd_toggle)
    p = sub.add_parser("model", help="change a section's model: spark40 model amp plexi")
    p.add_argument("slot", type=slot_arg)
    p.add_argument("name")
    p.add_argument("--force", action="store_true", help="send even if this firmware lacks the model")
    p = sub.add_parser("reverb", help="pick the reverb room: spark40 reverb 'plate rich'")
    p.add_argument("type")
    p = sub.add_parser("models", help="list amp and effect models (no amp needed)")
    p.add_argument("slot", nargs="?", type=slot_arg)
    p = sub.add_parser("backup", help="save the four presets and the current settings as JSON")
    p.add_argument("dir", nargs="?", help=f"folder (default: a dated folder in {BACKUP_DIR})")
    p = sub.add_parser("save", help="save the current settings as a JSON preset")
    p.add_argument("file")
    p.add_argument("--name", help="preset name to store in the file")
    p = sub.add_parser("load", help="play a JSON preset on the amp without saving it to a slot")
    p.add_argument("file")
    p.add_argument("--force", action="store_true", help="send even if this firmware lacks a model in it")
    p = sub.add_parser("cloud", help="search Positive Grid's ToneCloud, or play or save a preset from it")
    p.add_argument("keyword", nargs="?", help="song, artist, or style")
    p.add_argument("--order", choices=library.TONECLOUD_ORDERS, default="popular")
    p.add_argument("--count", type=int, default=20, help="results to show (default 20)")
    p.add_argument("--load", metavar="ID", help="play this preset on the amp")
    p.add_argument("--save", metavar="ID", help="save this preset to your presets folder")
    p.add_argument("--force", action="store_true", help="send even if this firmware lacks a model in it")
    return parser


COMMANDS = {
    "info": cmd_info, "dump": cmd_dump, "monitor": cmd_monitor, "preset": cmd_preset, "set": cmd_set,
    "model": cmd_model, "reverb": cmd_reverb, "backup": cmd_backup, "save": cmd_save, "load": cmd_load,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.debug:
        log.to_stderr()
        log.enable_debug(True)
    if args.command == "models":
        cmd_models(args)
        return 0
    if args.command == "cloud":
        try:
            return cmd_cloud(args)
        except OSError as err:
            print(f"Couldn't reach ToneCloud: {err}", file=sys.stderr)
            return 1
    func = getattr(args, "func", None) or COMMANDS[args.command]
    try:
        from .ble import SparkNotFound
    except ImportError:
        print("Bluetooth control needs PyGObject (python3-gobject).", file=sys.stderr)
        return 1
    try:
        with Spark.open(args.address) as spark:
            func(spark, args)
    except SparkNotFound as err:
        print(err, file=sys.stderr)
        return 1
    except SparkError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0
