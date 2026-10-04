# 0xSpark40

Native Linux control for the Positive Grid Spark 40 amp. Positive Grid's Spark app runs only on iOS and Android, and its firmware updater only on Windows and macOS. This project talks to the amp's Bluetooth LE control service directly, so you can read and change its settings from Linux: presets, amp and effect models, every knob, and the amp's own change reports. It also searches Positive Grid's ToneCloud, so you can play shared presets without a phone.

**Status:** 1.0. A GTK4 app, a command-line tool, and a Python library, tested on a Spark 40 running firmware 1.2.3.37 on Fedora 44.

## Install

Download `0xSpark40-1.0.0-x86_64.AppImage` from the [releases page](https://github.com/averagenative/0xSpark40/releases), make it executable, and run it:

```bash
chmod +x 0xSpark40-1.0.0-x86_64.AppImage
./0xSpark40-1.0.0-x86_64.AppImage --install
```

The AppImage is one standalone file: it bundles Python, GTK 4, libadwaita, and GStreamer, so it runs on any x86_64 desktop with glibc 2.41 or later (Fedora 42, Ubuntu 25.04, Debian 13, or later) without installing anything else. `--install` copies it to `~/Applications`, adds **0xSpark40** to your app grid with its icon, and links the `spark40` command into `~/.local/bin`. `--uninstall` removes that again. You can also run the AppImage directly without installing it; `./0xSpark40-1.0.0-x86_64.AppImage cli info` runs the command-line tool.

Everything the app saves lives in your home folder, so it's kept across AppImage updates: presets and backups in `~/Music/Spark Presets`, settings in `~/.config/spark40`, and downloads in `~/.cache/spark40`. `spark40 paths` lists them.

To install with pip instead, using your system's PyGObject, GTK, and libadwaita, download the wheel from the same page and run `pip install --user spark40-1.0.0-py3-none-any.whl`. That gives you the `spark40` command and the `spark40-gui` app.

## Requirements

- Linux with BlueZ and a Bluetooth adapter. The amp needs no pairing.
- Python 3.10 or later.
- PyGObject (`python3-gobject` on Fedora). The tool talks to BlueZ over D-Bus through it.
- For the app: GTK 4, libadwaita 1.7 or later, and GStreamer with the PipeWire plugin for the level meter. Fedora Workstation includes all of them.

Only one program can control the amp at a time. If a phone or tablet has the Spark app connected to the amp, close the app first.

## How the amp connects

The Spark 40 shows up as two devices over USB and two over Bluetooth, and each one has a different job:

| Link | Shows up as | Use |
|---|---|---|
| Bluetooth LE | `Spark 40 BLE` | Control: everything this project does. |
| Bluetooth Classic | `Spark 40 Audio` | A Bluetooth speaker for backing tracks. |
| USB audio | `Spark 40 USB` | Recording: mono, 16-bit, 48 kHz in; stereo out to the amp's speakers. |
| USB MIDI | `Spark 40` | Firmware updates only. The amp ignores control commands here. |

## The app

Start the app from the repository:

```bash
python3 -m spark40.gui
```

From a clone, run `make install` once to add **0xSpark40** to your GNOME app grid with an icon. `python3 -m spark40.gui --demo` opens the window with sample settings and no amp.

The window finds the amp over Bluetooth by itself and follows the signal chain from top to bottom:

- **Noise Gate, Compressor, and Drive:** each with an on/off switch, a model picker, and that model's knobs.
- **Amp:** the amp model and its five knobs, beside the **Recording level** meter for the USB input.
- **Modulation, Delay, and Reverb:** the reverb picker chooses the room (Room Studio A to Plate Long).
- **Presets:** the four presets stored on the amp. Click one to switch to it. **Save to preset...** stores the current sound in the preset you pick, under the name you choose; it does the same job as holding a preset button on the amp. Before it replaces a preset, the app saves the old one to `~/Music/Spark Presets/Backups/Replaced`.

The window mirrors the amp: turn a knob or press a preset button on the amp, and the window follows. It reconnects by itself when the amp turns off and on. Model pickers list only the models your firmware has.

Each knob responds to dragging, the scroll wheel, and the arrow keys. **Knob step** sets how far one scroll notch or arrow-key press moves a knob: 0.1, 0.2, 0.5, or 1. Hold Shift to move by 0.1.

**Record** in the header bar picks what the computer records over USB. **Dry** switches every block off, including the amp, so you can record a dry guitar track for reamping; the speaker plays the dry signal too. **Amp** switches the blocks back on.

Changing the amp model keeps your Gain, Treble, Middle, Bass, and Volume unless you clear **Keep knobs when changing amps**. Other blocks start from the new model's default settings.

The palette button picks a theme. The Spark finishes (Spark 40 Black, Spark 40 Pearl, Spark 2, Spark MINI Vai Red, and Spark LIVE) and the tolex colors (Emerald, Purple, and Blue) dress the panels in tolex with piping and put the grille cloth at the bottom. Adwaita follows your desktop's style.

The Console button opens a live log of connections and errors. Turn on **Debug** in the console to log every block sent to and received from the amp.

### Presets

Click **Presets** in the header bar for three sources:

- **Yours:** JSON preset files in `~/Music/Spark Presets`. Save the current sound under a name, or back up the amp's four presets to a dated folder.
- **ToneCloud:** search Positive Grid's ToneCloud by song, artist, or style, sorted by downloads, date, or name. Searching and downloading need no account.
- **Community:** the song and artist presets collected by [Ignitron](https://github.com/stangreg/Ignitron), downloaded to your computer the first time you ask.

Click a preset to play it on the amp. The save button keeps a copy in your presets. Playing a preset doesn't change the four stored presets; to keep it on the amp, click **Save to preset...** in the main window, or hold a preset button on the amp for two seconds. **Keep my amp volume** (on by default) plays a preset's sound with your current amp Volume, so a loud preset doesn't jump out.

Presets that use models your firmware doesn't have are greyed out, with the missing models listed. Many early ToneCloud presets use model names from other Positive Grid products (`Noisegate`, `FreeVerb`, `GraphicalEQ7`), which a Spark 40 can't load.

ToneCloud's API is undocumented; it's the one the Spark app uses. Positive Grid can change it at any time.

## Command line

Turn the amp on, and then run any of these from the repository:

```bash
python3 -m spark40 info
python3 -m spark40 dump
python3 -m spark40 monitor
```

With the AppImage installed, the command is `spark40`; from a clone, use `python3 -m spark40`. `spark40 paths` shows where settings, presets, and caches are stored.

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

Changes affect the sound the amp is playing. They don't change a stored preset until you store them with `store` or hold that preset's button on the amp for two seconds.

```bash
python3 -m spark40 store 2 --name "My crunch"
python3 -m spark40 store 4 --file "my lead.json"
```

`store` replaces stored preset 1 to 4 with the current sound, or with a preset file, and reads it back to check. It saves the preset it replaces to `~/Music/Spark Presets/Backups/Replaced` first.

### Presets

```bash
python3 -m spark40 backup
python3 -m spark40 save "my crunch.json"
python3 -m spark40 load "my crunch.json"
```

`backup` saves the four stored presets and the current settings to a dated folder in `~/Music/Spark Presets/Backups`. `save` writes the current settings to a file, and `load` plays a preset file on the amp without touching the stored presets. The files use the JSON preset format of [Ignitron](https://github.com/stangreg/Ignitron) and Paul Hamshere's tools, so presets move between them.

To search ToneCloud and play or save a result:

```bash
python3 -m spark40 cloud "sultans of swing"
python3 -m spark40 cloud --load 5ed762a824096c001661d22c
python3 -m spark40 cloud --save 5ed762a824096c001661d22c
```

Searching and `--save` work without the amp. Results that need models a Spark 40 lacks are marked.

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
| `spark40/library.py` | Your preset folder, the community collection, and ToneCloud search and download |
| `spark40/cli.py` | The `spark40` command |
| `spark40/log.py` | Logging and raw block tracing |
| `spark40/gui/worker.py` | Background thread that owns the connection, coalesces knob moves, and forwards the amp's change reports |
| `spark40/gui/window.py` | The libadwaita window |
| `spark40/gui/presets.py` | The presets dialog: your files, ToneCloud, and the community collection |
| `spark40/gui/knob.py` | Rotary knob control with drag, scroll, and keyboard input and a shared step setting |
| `spark40/gui/themes.py` | Themes: tolex, piping, grille cloth, knob styles, and libadwaita color variables |
| `spark40/gui/meter.py` | USB recording level meter: `pipewiresrc ! level`, pinned to the amp's capture node |

See `docs/protocol.md` for the message format and what this project learned about the amp's USB side.

## Credits

The protocol knowledge comes from [Paul Hamshere's Spark protocol description](https://github.com/paulhamsh/Spark) and the community projects built on it. The ToneCloud client follows [Soundshed](https://github.com/soundshed/soundshed-app)'s. The knob, meter, console, and link lights come from [0xTHR-II](https://github.com/averagenative/0xTHR-II). The model table merges [Soundshed's FX catalog](https://github.com/soundshed/soundshed-app) (MIT) and [Ignitron's parameter reference](https://github.com/stangreg/Ignitron) (BSD-3-Clause). The USB MIDI notes build on [Ian McKellar's Spark 40 USB MIDI analysis](https://git.sr.ht/~ianloic/spark-usb-midi).

Positive Grid and Spark are trademarks of Positive Grid LLC. This project isn't affiliated with or endorsed by Positive Grid.

## License

MIT. See `LICENSE`.
