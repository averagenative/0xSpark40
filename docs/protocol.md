# Spark 40 protocol notes

These notes summarize the control protocol as this project uses it, and record what was learned by probing a Spark 40 on firmware 1.2.3.37. For the full message reference, see Paul Hamshere's `Spark Protocol Description` in [paulhamsh/Spark](https://github.com/paulhamsh/Spark).

## Bluetooth LE service

The amp advertises as `Spark 40 BLE` and accepts connections without pairing. It accepts one client at a time.

| UUID | Use |
|---|---|
| `0000ffc0-...` | Control service |
| `0000ffc1-...` | Write: blocks from the app to the amp |
| `0000ffc2-...` | Notify: blocks from the amp |

The negotiated ATT MTU on Fedora 44 with BlueZ is 200, so every block fits in one write and one notification. The decoder still buffers blocks that arrive split, in case of a smaller MTU.

## Framing

A message has a command, a sub-command, and a payload. It travels in a chunk, and chunks travel in blocks.

A block starts with a 16-byte header: `01 fe 00 00`, a direction (`53 fe` to the amp, `41 ff` from the amp), the block length including the header, and nine zero bytes.

A chunk is `f0 01 <seq> <checksum> <cmd> <sub> <data> f7`. The data is the payload packed to 7-bit bytes: each group of up to seven bytes is preceded by a byte that holds their top bits. The checksum is the XOR of the packed data. Replies and acknowledgements carry the sequence number of the request they answer.

The app numbers its messages from `0x01` to `0x3e` and then wraps; the amp numbers its own change reports from `0x40`. Each chunk of a preset sent to the amp takes the next sequence number, and the amp acknowledges each chunk with `04 01` under that number. With one sequence number repeated across the chunks, the amp acknowledged every chunk but never applied the preset. The amp itself repeats one sequence number across the chunks of a preset it sends.

Bluetooth writes of a whole 173-byte block fail with `org.bluez.Error.InvalidArguments: Invalid Length`, so blocks go out in writes of at most 100 bytes. The amp reassembles them from the block length in the header.

Only presets span chunks. Each chunk's data then starts with three bytes: the chunk count, the chunk index, and the number of payload bytes in the chunk. The app sends up to 128 payload bytes per chunk, one chunk per block of at most 173 bytes. The amp sends 25 payload bytes per chunk and packs several chunks into each block of at most 106 bytes.

## Commands

The following table lists the commands this project uses:

| Command | Direction | Meaning | Payload |
|---|---|---|---|
| `02 11` | to amp | Get the amp's name | none; reply is a string |
| `02 23` | to amp | Get the serial number | none; reply is a string with a trailing `0xf7` byte |
| `02 2f` | to amp | Get the firmware version | none; reply is a 4-byte integer, one byte per version part |
| `02 10` | to amp | Get the active stored preset | none; reply is `00 <preset>` |
| `02 01` | to amp | Get a preset | `00 <0-3>` for a stored preset, `01 00` for the live settings, then 35 zero bytes |
| `01 38` | to amp | Switch preset | `00 <0-3>`, or `00 7f` for the live slot |
| `01 04` | to amp | Set a knob | effect name, parameter index, float from 0.0 to 1.0; not acknowledged |
| `01 15` | to amp | Switch an effect on or off | effect name, boolean |
| `01 06` | to amp | Change a model | old effect name, new effect name |
| `01 01` | to amp | Send a preset | the preset (multi-chunk); each chunk is acknowledged |
| `03 37` | from amp | A knob turned on the amp | effect name, parameter index, float |
| `03 38` | from amp | A preset button pressed on the amp | `00 <preset>` |
| `03 27` | from amp | The current sound stored to a preset on the amp | `00 <preset>` |
| `04 xx` | from amp | Acknowledges command `01 xx` | usually empty |

Effect names in `01 04`, `01 15`, `01 06`, and `03 37` use a *prefixed string*: a length byte, then a msgpack short string (`0xa0 + length`, then the characters).

## Presets

A preset payload is two bytes (a current-settings flag and the slot), the UUID as a msgpack `str8`, short strings for the name, version, description, and icon, a float for the BPM, and an array of seven pedals. Each pedal is a name, a boolean, and an array of parameters; each parameter is its index followed by a one-element array holding a float. The last byte is the sum of every byte after the first two, modulo 256.

The pedals are always in this order: noise gate, compressor, drive, amp, modulation, delay, reverb. On firmware 1.2.3.37, every reverb is the model `bias.reverb`, and its seventh parameter picks the room as type index / 10. The live settings can report more parameters per pedal than a stored preset does: the noise gate reported three and the reverb eight.

`spark40.preset.Preset.encode` reproduces the amp's own preset bytes exactly; the tests check this against presets read from the amp.

To store a preset, send it with `01 01` and slot 0 to 3 in its header, then switch to that slot with `01 38 00 <slot>`. Reading the slot back with `02 01 00 <slot>` returns the new preset, and it is still there after a reconnect. Whether it survives turning the amp off and on is not yet tested.

To play a preset without storing it, send it to slot `0x7f` with `01 01`, then switch to that slot with `01 38 00 7f`. Sending alone doesn't change the sound. The amp keeps playing the live slot after the Bluetooth connection closes, and `02 10` then reports `0x7f` as the active preset.

## Amp model changes

Changing the amp model, from the app with `01 06` or with the amp selector knob on the Spark (reported as `03 06`), loads the new model's default knobs. Plexiglas, for example, starts at Volume 3.4 whatever the previous amp's Volume was. Paul Hamshere's notes say the Spark app answers `03 06` by sending five `01 04` parameter changes. This project does the same with the previous model's Gain, Treble, Middle, Bass, and Volume, so the volume doesn't jump.

## USB

The Spark 40 contains a USB hub with two devices.

The audio device (`10d6:1319`, an Actions Semiconductor chip) is a class-compliant UAC1 interface at full speed: one capture channel and two playback channels, 16-bit, 48 kHz.

The MIDI device (`ffff:ffff`, product `Spark 40`) carries Positive Grid's firmware updater protocol. It uses the same chunk format without the block header, for example `f0 01 00 00 02 11 f7`. The amp answers only the updater's queries: `02 11` (name), `02 12`, `02 23` (serial number), and ASCII commands such as `GetFwInfo`. It ignores preset and parameter commands, and it sends nothing when knobs turn. It also accepts the updater's `WriteFlash` command, so send nothing over USB MIDI beyond known read-only queries.

## Firmware updater under Wine

On 2026-10-04, Positive Grid's Windows updater for 1.10.8.25 ran under Wine 11.0 against this amp. The updater is a JUCE app that reaches the amp only through the Windows MIDI API (`WINMM.dll`), which Wine maps to ALSA. It detected the amp, read its firmware version, and sent `SetFwStatus 00`.

The amp then restarted into its bootloader, which enumerates as the same `ffff:ffff` device with product name `G1` and repeats `RetFwStatus 00` about five times a second. The updater asked it for `GetFwInfo` about three seconds after it appeared. The bootloader never answered, either to the updater or to the same request sent directly with `aseqsend`, although the kernel reported the bytes as transmitted. No `WriteFlash` was sent. Turning the amp off and on returned it to normal mode with its firmware unchanged.

In Ian McKellar's capture of a working update, the bootloader repeats `RetFwStatus 00` 23 times before the updater's `GetFwInfo` gets a reply. The Linux USB MIDI path to the bootloader may need something that Windows and macOS do, such as a USB control request, before it accepts commands. To update the firmware, use a Mac, Windows 10, or Windows 11 24H2 or earlier. Positive Grid reports that Windows 11 25H2 also breaks the updater.
