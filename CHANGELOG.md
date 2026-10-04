# Changelog

## 1.0.0 (2026-10-04)

First release. Tested on a Spark 40 with firmware 1.2.3.37 on Fedora 44.

### Downloads

- `0xSpark40-1.0.0-x86_64.AppImage` is a single standalone file: it bundles Python 3.13, GTK 4, libadwaita, and GStreamer, so it runs without installing anything on any x86_64 desktop with glibc 2.41 or later (Fedora 42, Ubuntu 25.04, Debian 13, or later). `--install` adds it to the app grid with its icon and links `spark40` into `~/.local/bin`; `--uninstall` removes that; `cli` runs the command-line tool.
- The wheel and source archive install the app and the `spark40` command with pip, using your system's PyGObject, GTK, and libadwaita.

### Amp control

- Bluetooth LE control through BlueZ, with no pairing. The amp's USB MIDI port only carries firmware updates, so it isn't used.
- Reads and changes every block of the signal chain: noise gate, compressor, drive, amp, modulation, delay, and reverb, with their models, on/off switches, and knobs.
- Follows knob turns, preset buttons, effect toggles, and amp changes made on the amp.
- Refuses amp and effect models the amp's firmware doesn't have, since Positive Grid warns they crash it.
- Changing the amp model, in the app or with the amp knob on the Spark, keeps Gain, Treble, Middle, Bass, and Volume, so the volume doesn't jump.

### Presets

- Switches between the four stored presets, and saves the current sound to any of them under a name you choose. The preset it replaces is saved to a file first, and the result is read back to check.
- Plays presets from three sources without touching the stored presets: your JSON files, Positive Grid's ToneCloud (search and download need no account), and the song presets collected by the Ignitron project.
- Backs up the amp's four presets, and saves the current sound, as JSON in the format Ignitron and Paul Hamshere's tools use.
- Keep my amp volume plays a preset's sound with your current amp Volume.

### App

- One-screen GTK4 and libadwaita window laid out in signal-chain order, with rotary knobs and an adjustable knob step.
- USB recording level meter with peak hold and a clip warning, and a Dry mode that switches every block off to record a dry guitar for reamping.
- Themes: Spark 40 Black, Spark 40 Pearl, Spark 2, Spark MINI Vai Red, Spark LIVE, Emerald, Purple, Blue, Neon, Bare Metal, and Adwaita.
- Bluetooth and USB link lights, and a console with a debug switch for raw Bluetooth blocks.

### Command line

- `spark40` with `info`, `dump`, `monitor`, `preset`, `set`, `on`, `off`, `model`, `reverb`, `models`, `backup`, `save`, `load`, `store`, `cloud`, and `paths`, plus `--debug`.

### Known limitations

- Whether a preset saved from the app survives turning the amp off and on hasn't been tested yet.
- Firmware updates still need Positive Grid's updater on macOS or Windows. Under Wine the amp's bootloader doesn't answer; see `docs/protocol.md`.
- The order of four reverb knobs (Dwell, Time, Low Cut, High Cut) comes from community notes that disagree, and hasn't been checked by ear.
