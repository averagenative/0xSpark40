# 0xSpark40

Native Linux control for the Positive Grid Spark 40 amp. Positive Grid's Spark app runs only on iOS and Android, and its firmware updater only on Windows and macOS. This project talks to the amp's Bluetooth LE control service directly, so you can read and change its settings from Linux: presets, amp and effect models, every knob, and the amp's own change reports.

**Status:** 0.1. A Python library and a command-line tool, tested on a Spark 40 running firmware 1.2.3.37 on Fedora 44. A GTK4 app, like the one in [0xTHR-II](https://github.com/averagenative/0xTHR-II), comes next.

## Requirements

- Linux with BlueZ and a Bluetooth adapter. The amp needs no pairing.
- Python 3.10 or later.
- PyGObject (`python3-gobject` on Fedora). The tool talks to BlueZ over D-Bus through it.

Only one program can control the amp at a time. If a phone or tablet has the Spark app connected to the amp, close the app first.

## How the amp connects

The Spark 40 shows up as two devices over USB and two over Bluetooth, and each one has a different job:

| Link | Shows up as | Use |
|---|---|---|
| Bluetooth LE | `Spark 40 BLE` | Control: everything this project does. |
| Bluetooth Classic | `Spark 40 Audio` | A Bluetooth speaker for backing tracks. |
| USB audio | `Spark 40 USB` | Recording: mono, 16-bit, 48 kHz in; stereo out to the amp's speakers. |
| USB MIDI | `Spark 40` | Firmware updates only. The amp ignores control commands here. |

## Command line

Turn the amp on, and then run any of these from the repository:

```bash
python3 -m spark40 info
python3 -m spark40 dump
python3 -m spark40 monitor
```

`info` shows the name, serial number, firmware, and the four stored presets, with a star on the active one. `dump` shows the settings the amp is playing right now, including changes you haven't saved; `dump 2` shows stored preset 2 instead. `monitor` prints changes as you turn knobs or press preset buttons on the amp.

To change settings:

```bash
python3 -m spark40 preset 3
python3 -m spark40 set amp gain 6.5
python3 -m spark40 set delay feedback 3
python3 -m spark40 on mod
python3 -m spark40 off drive
python3 -m spark40 model amp plexi
python3 -m spark40 reverb "plate rich"
```

Values are 0 to 10, like the Spark app. The sections are `gate`, `comp`, `drive`, `amp`, `mod`, `delay`, and `reverb`. Knob names match the Spark app's labels, and a unique prefix is enough (`set amp vol 4`). `python3 -m spark40 models` lists every amp and effect, and works without the amp.

Changes affect the sound the amp is playing. They don't change a stored preset until you hold that preset's button on the amp for two seconds.

### Presets

```bash
python3 -m spark40 backup
python3 -m spark40 save "my crunch.json"
python3 -m spark40 load "my crunch.json"
```

`backup` saves the four stored presets and the current settings to a dated folder in `~/Music/Spark Presets/Backups`. `save` writes the current settings to a file, and `load` plays a preset file on the amp without touching the stored presets. The files use the JSON preset format of [Ignitron](https://github.com/stangreg/Ignitron) and Paul Hamshere's tools, so presets move between them.

### Firmware and models

Positive Grid added amps and effects in later firmware: ODS 50, Blues Boy, Insane 6508, Clone Drive, and the Guitar and Bass EQs in 1.4.3.174, and the Experience Jimi Hendrix pack in 1.5.4.102. Positive Grid warns that a preset slot holding a model the running firmware doesn't have crashes the amp. `model` and `load` check the amp's firmware and refuse such models; `--force` overrides the check. `models` marks the models that need later firmware.

## Recording through the Spark

The Spark 40 is a class-compliant USB audio interface, so it works with any Linux recording program with no driver:

- **Input:** one channel, 16-bit, 48 kHz. PipeWire names it `Spark 40 USB Mono`.
- **Output:** two channels at 48 kHz, played through the amp's speakers.
- **Signal:** the amp's processed tone. The Spark 40 has no separate dry output; to record a dry signal for reamping, switch off every section including the amp, which also makes the speaker play the dry signal.

## Debug output

Add `--debug` before the command to log every block sent to and received from the amp, as hex: `python3 -m spark40 --debug info`.

## How it works

The following table describes each module:

| Module | Role |
|---|---|
| `spark40/protocol.py` | Blocks, chunks, 7-bit packing, checksums, multi-chunk presets, and the amp's msgpack-like values |
| `spark40/preset.py` | Presets in the amp's binary form and as JSON |
| `spark40/catalog.py` | Amp and effect models: display names, knob labels, defaults, and the firmware each needs |
| `spark40/ble.py` | Bluetooth LE transport through BlueZ over D-Bus, with a reader thread |
| `spark40/client.py` | Queries, changes, acknowledgements, and the amp's change reports |
| `spark40/cli.py` | The `spark40` command |
| `spark40/log.py` | Logging and raw block tracing |

See `docs/protocol.md` for the message format and what this project learned about the amp's USB side.

## Credits

The protocol knowledge comes from [Paul Hamshere's Spark protocol description](https://github.com/paulhamsh/Spark) and the community projects built on it. The model table merges [Soundshed's FX catalog](https://github.com/soundshed/soundshed-app) (MIT) and [Ignitron's parameter reference](https://github.com/stangreg/Ignitron) (BSD-3-Clause). The USB MIDI notes build on [Ian McKellar's Spark 40 USB MIDI analysis](https://git.sr.ht/~ianloic/spark-usb-midi).

Positive Grid and Spark are trademarks of Positive Grid LLC. This project isn't affiliated with or endorsed by Positive Grid.

## License

MIT. See `LICENSE`.
