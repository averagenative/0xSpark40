"""Amp and effect models: internal names, display names, knob labels, and the firmware each needs.

Merged from two community tables: Soundshed's FX catalog (MIT, github.com/soundshed/soundshed-app)
for defaults, and Ignitron's parameter reference (BSD-3-Clause, github.com/stangreg/Ignitron) for
knob labels and which knobs are switches. Values on the wire are 0.0 to 1.0; the Spark app shows
them as 0 to 10.

``since`` is the first Spark 40 firmware with the model. Positive Grid warns that a preset slot
holding a model newer than the running firmware crashes it, so the client refuses to send one.
``OTHER`` marks models from other Spark amps (Spark 2, MINI, GO, LIVE) that the Spark 40 lacks.
"""

from __future__ import annotations

from dataclasses import dataclass

SLOTS = ("gate", "comp", "drive", "amp", "mod", "delay", "reverb")
SLOT_NAMES = {"gate": "Noise Gate", "comp": "Compressor", "drive": "Drive", "amp": "Amp",
              "mod": "Modulation", "delay": "Delay", "reverb": "Reverb"}

BASE = (0, 0, 0, 0)
OTHER = (99, 0, 0, 0)

# Reverb is one model, "bias.reverb", on every Spark 40 firmware. Its seventh parameter picks the
# room: type index / 10. The order of parameters 2 to 5 differs between the two source tables;
# this follows Ignitron's. Not yet confirmed by ear.
REVERB = "bias.reverb"
REVERB_TYPE_PARAM = 6
REVERB_TYPES = ("Room Studio A", "Room Studio B", "Chamber", "Hall Natural", "Hall Medium",
                "Hall Ambient", "Plate Short", "Plate Rich", "Plate Long")


@dataclass(frozen=True)
class Param:
    name: str
    default: float = 0.5
    switch: bool = False


@dataclass(frozen=True)
class Model:
    id: str
    slot: str
    name: str
    params: tuple[Param, ...]
    since: tuple[int, int, int, int] = BASE

    def supported_by(self, firmware: tuple[int, ...] | None) -> bool:
        return self.since != OTHER and (firmware is None or tuple(firmware) >= self.since)


def _m(slot: str, model_id: str, name: str, params: list, since=BASE) -> Model:
    return Model(model_id, slot, name, tuple(Param(*p) for p in params), since)


_FW_1_4 = (1, 4, 3, 174)
_FW_1_5 = (1, 5, 4, 102)

_MODELS = [
    _m('gate', 'bias.noisegate', 'Noise Gate', [('Threshold', 0.2), ('Decay', 0.1)]),
    _m('comp', 'LA2AComp', 'LA Comp', [('Limit/Compress', 0.0, True), ('Gain', 0.7), ('Peak Reduction', 0.7)]),
    _m('comp', 'BlueComp', 'Sustain Comp', [('Level', 0.5), ('Tone', 0.5), ('Attack', 0.5), ('Sustain', 0.6)]),
    _m('comp', 'Compressor', 'Red Comp', [('Output', 0.4), ('Sensitivity', 0.6)]),
    _m('comp', 'BassComp', 'Bass Comp', [('Comp', 0.4), ('Gain', 0.5)]),
    _m('comp', 'BBEOpticalComp', 'Optical Comp', [('Volume', 0.7), ('Comp', 0.4), ('Pad', 0.0, True)]),
    _m('drive', 'Booster', 'Booster', [('Gain', 0.8)]),
    _m('drive', 'KlonCentaurSilver', 'Clone Drive', [('Output', 1.0), ('Treble', 0.5), ('Gain', 0.5)], _FW_1_4),
    _m('drive', 'DistortionTS9', 'Tube Drive', [('Overdrive', 0.6), ('Tone', 0.5), ('Level', 0.6)]),
    _m('drive', 'Overdrive', 'Over Drive', [('Level', 0.6), ('Tone', 0.7), ('Drive', 0.5)]),
    _m('drive', 'Fuzz', 'Fuzz Face', [('Volume', 0.4), ('Fuzz', 0.8)]),
    _m('drive', 'ProCoRat', 'Black Op', [('Distortion', 0.7), ('Filter', 0.5), ('Volume', 0.7)]),
    _m('drive', 'BassBigMuff', 'Bass Muff', [('Volume', 0.3), ('Tone', 0.8), ('Sustain', 0.9)]),
    _m('drive', 'GuitarMuff', 'Guitar Muff', [('Volume', 0.5), ('Tone', 0.5), ('Sustain', 0.8)]),
    _m('drive', 'MaestroBassmaster', 'Bassmaster', [('Brass Volume', 0.4), ('Sensitivity', 0.8), ('Bass Volume', 0.2)]),
    _m('drive', 'SABdriver', 'SAB Driver', [('Volume', 0.4), ('Tone', 0.5), ('Drive', 0.8), ('LP/HP', 0.0, True)]),
    _m('amp', 'RolandJC120', 'Silver 120', [('Gain', 0.7), ('Treble', 0.4), ('Middle', 0.3), ('Bass', 0.5), ('Volume', 0.8)]),
    _m('amp', 'Twin', 'Black Duo', [('Gain', 0.7), ('Treble', 0.4), ('Middle', 0.5), ('Bass', 0.5), ('Volume', 0.8)]),
    _m('amp', 'ADClean', 'AD Clean', [('Gain', 0.7), ('Treble', 0.6), ('Middle', 0.5), ('Bass', 0.3), ('Volume', 0.7)]),
    _m('amp', '94MatchDCV2', 'Match DC', [('Gain', 0.5), ('Treble', 0.4), ('Middle', 0.4), ('Bass', 0.4), ('Volume', 0.7)]),
    _m('amp', 'ODS50CN', 'ODS 50', [('Gain', 0.5), ('Treble', 0.6), ('Middle', 0.4), ('Bass', 0.5), ('Volume', 0.7)], _FW_1_4),
    _m('amp', 'BluesJrTweed', 'Blues Boy', [('Gain', 0.5), ('Treble', 0.6), ('Middle', 0.4), ('Bass', 0.5), ('Volume', 0.7)], _FW_1_4),
    _m('amp', 'Bassman', 'Tweed Bass', [('Gain', 0.6), ('Treble', 0.7), ('Middle', 0.5), ('Bass', 0.4), ('Volume', 0.7)]),
    _m('amp', 'AC Boost', 'AC Boost', [('Gain', 0.5), ('Treble', 0.5), ('Middle', 0.5), ('Bass', 0.5), ('Volume', 0.5)]),
    _m('amp', 'Checkmate', 'Checkmate', [('Gain', 0.7), ('Treble', 0.5), ('Middle', 0.4), ('Bass', 0.5), ('Volume', 0.4)]),
    _m('amp', 'TwoStoneSP50', 'Two Stone SP50', [('Gain', 0.6), ('Treble', 0.5), ('Middle', 0.6), ('Bass', 0.5), ('Volume', 0.7)]),
    _m('amp', 'Deluxe65', 'American Deluxe', [('Gain', 0.7), ('Treble', 0.4), ('Middle', 0.2), ('Bass', 0.6), ('Volume', 0.7)]),
    _m('amp', 'Plexi', 'Plexiglas', [('Gain', 0.7), ('Treble', 0.4), ('Middle', 0.5), ('Bass', 0.6), ('Volume', 0.3)]),
    _m('amp', 'OverDrivenJM45', 'JM45', [('Gain', 0.7), ('Treble', 0.5), ('Middle', 0.3), ('Bass', 0.6), ('Volume', 0.7)]),
    _m('amp', 'OverDrivenLuxVerb', 'Lux Verb', [('Gain', 0.3), ('Treble', 0.2), ('Middle', 0.3), ('Bass', 0.4), ('Volume', 0.8)]),
    _m('amp', 'Bogner', 'RB 101', [('Gain', 0.7), ('Treble', 0.6), ('Middle', 0.6), ('Bass', 0.4), ('Volume', 0.5)]),
    _m('amp', 'OrangeAD30', 'British 30', [('Gain', 0.7), ('Treble', 0.4), ('Middle', 0.4), ('Bass', 0.6), ('Volume', 0.3)]),
    _m('amp', 'AmericanHighGain', 'American High Gain', [('Gain', 0.6), ('Treble', 0.4), ('Middle', 0.6), ('Bass', 0.5), ('Volume', 0.8)]),
    _m('amp', 'SLO100', 'SLO 100', [('Gain', 0.6), ('Treble', 0.4), ('Middle', 0.5), ('Bass', 0.5), ('Volume', 0.5)]),
    _m('amp', 'YJM100', 'YJM100', [('Gain', 0.6), ('Treble', 0.5), ('Middle', 0.4), ('Bass', 0.6), ('Volume', 0.6)]),
    _m('amp', 'Rectifier', 'Treadplate', [('Gain', 0.7), ('Treble', 0.6), ('Middle', 0.6), ('Bass', 0.6), ('Volume', 0.8)]),
    _m('amp', 'EVH', 'Insane', [('Gain', 0.5), ('Treble', 0.7), ('Middle', 0.6), ('Bass', 0.3), ('Volume', 0.9)]),
    _m('amp', '6505Plus', 'Insane 6508', [('Gain', 0.5), ('Treble', 0.6), ('Middle', 0.4), ('Bass', 0.5), ('Volume', 0.7)], _FW_1_4),
    _m('amp', 'SwitchAxeLead', 'SwitchAxe', [('Gain', 0.6), ('Treble', 0.5), ('Middle', 0.5), ('Bass', 0.6), ('Volume', 0.7)]),
    _m('amp', 'Invader', 'Rocker V', [('Gain', 0.6), ('Treble', 0.5), ('Middle', 0.4), ('Bass', 0.6), ('Volume', 0.6)]),
    _m('amp', 'BE101', 'BE 101', [('Gain', 0.6), ('Treble', 0.6), ('Middle', 0.6), ('Bass', 0.4), ('Volume', 0.8)]),
    _m('amp', 'Acoustic', 'Pure Acoustic', [('Gain', 0.6), ('Treble', 0.5), ('Middle', 0.5), ('Bass', 0.5), ('Volume', 0.5)]),
    _m('amp', 'AcousticAmpV2', 'Fishboy', [('Gain', 0.4), ('Treble', 0.4), ('Middle', 0.1), ('Bass', 0.7), ('Volume', 0.8)]),
    _m('amp', 'FatAcousticV2', 'Jumbo', [('Gain', 0.5), ('Treble', 0.5), ('Middle', 0.5), ('Bass', 0.7), ('Volume', 0.5)]),
    _m('amp', 'FlatAcoustic', 'Flat Acoustic', [('Gain', 0.7), ('Treble', 0.4), ('Middle', 0.6), ('Bass', 0.7), ('Volume', 0.5)]),
    _m('amp', 'GK800', 'RB-800', [('Gain', 0.5), ('Treble', 0.4), ('Middle', 0.4), ('Bass', 0.6), ('Volume', 0.9)]),
    _m('amp', 'Sunny3000', 'Sunny 3000', [('Gain', 0.5), ('Treble', 0.6), ('Middle', 0.4), ('Bass', 0.5), ('Volume', 0.7)]),
    _m('amp', 'W600', 'W600', [('Gain', 0.5), ('Treble', 0.4), ('Middle', 0.3), ('Bass', 0.6), ('Volume', 0.9)]),
    _m('amp', 'Hammer500', 'Hammer 500', [('Gain', 0.5), ('Treble', 0.5), ('Middle', 0.3), ('Bass', 0.7), ('Volume', 0.8)]),
    _m('mod', 'Tremolo', 'Tremolo', [('Speed', 0.5), ('Depth', 0.7), ('Level', 0.6)]),
    _m('mod', 'ChorusAnalog', 'Chorus', [('E.Level', 0.8), ('Rate', 0.3), ('Depth', 0.7), ('Tone', 0.6)]),
    _m('mod', 'Flanger', 'Flanger', [('Rate', 0.4), ('Mix', 0.7), ('Depth', 0.7)]),
    _m('mod', 'Phaser', 'Phaser', [('Speed', 0.6), ('Intensity', 0.6)]),
    _m('mod', 'Vibrato01', 'Vibrato', [('Speed', 0.8), ('Depth', 0.5)]),
    _m('mod', 'UniVibe', 'UniVibe', [('Speed', 0.5), ('Vibrato/Chorus', 1.0, True), ('Intensity', 0.7)]),
    _m('mod', 'Cloner', 'Cloner Chorus', [('Rate', 0.2), ('Depth', 1.0, True)]),
    _m('mod', 'MiniVibe', 'Classic Vibe', [('Speed', 0.3), ('Intensity', 0.3)]),
    _m('mod', 'Tremolator', 'Tremolator', [('Depth', 0.7), ('Speed', 0.5), ('BPM On/Off', 0.0, True)]),
    _m('mod', 'TremoloSquare', 'Tremolo Square', [('Speed', 0.5), ('Depth', 0.7), ('Level', 0.6)]),
    _m('mod', 'GuitarEQ6', 'Guitar EQ', [('Level', 0.5), ('100', 0.5), ('200', 0.5), ('400', 0.5), ('800', 0.5), ('1.6k', 0.5), ('3.2k', 0.5)], _FW_1_4),
    _m('mod', 'BassEQ6', 'Bass EQ', [('Level', 0.5), ('50', 0.5), ('120', 0.5), ('400', 0.5), ('800', 0.5), ('4.5k', 0.5), ('10k', 0.5)], _FW_1_4),
    _m('delay', 'DelayMono', 'Digital Delay', [('E.Level', 0.4), ('Feedback', 0.4), ('DelayTime', 0.7), ('Mode', 0.6), ('BPM', 0.0, True)]),
    _m('delay', 'DelayEchoFilt', 'Echo Filt', [('Delay', 0.2), ('Feedback', 0.5), ('Level', 0.7), ('Tone', 0.5), ('BPM', 0.0, True)]),
    _m('delay', 'VintageDelay', 'Vintage Delay', [('Repeat Rate', 0.3), ('Intensity', 0.6), ('Echo', 0.7), ('BPM', 1.0, True)]),
    _m('delay', 'DelayReverse', 'Reverse Delay', [('Mix', 0.7), ('Decay', 0.4), ('Filter', 0.7), ('Time', 0.6), ('BPM', 0.0, True)]),
    _m('delay', 'DelayMultiHead', 'Multi Head', [('Repeat Rate', 0.6), ('Intensity', 0.6), ('Echo Volume', 0.5), ('Mode Selector', 0.6), ('BPM', 0.0, True)]),
    _m('delay', 'DelayRe201', 'Echo Tape', [('Sustain', 0.5), ('Volume', 0.5), ('Tone', 0.5), ('Short/Long', 0.5)]),
    _m('amp', 'JCM800', 'JCM 800', [('Gain', 0.5), ('Treble', 0.6), ('Middle', 0.4), ('Bass', 0.5), ('Master', 0.7)], OTHER),
    _m('amp', 'MatchlessDC30', 'Matchless DC30', [('Gain', 0.5), ('Treble', 0.6), ('Middle', 0.4), ('Bass', 0.5), ('Master', 0.7)], OTHER),
    _m('amp', 'DrZ', 'Dr. Z', [('Gain', 0.5), ('Treble', 0.6), ('Middle', 0.4), ('Bass', 0.5), ('Master', 0.7)], OTHER),
    _m('amp', 'Hiwatt103', 'Hiwatt DR103', [('Gain', 0.5), ('Treble', 0.6), ('Middle', 0.4), ('Bass', 0.5), ('Master', 0.7)], OTHER),
    _m('amp', 'B15', 'B-15', [('Gain', 0.5), ('Treble', 0.6), ('Middle', 0.4), ('Bass', 0.5), ('Master', 0.7)], OTHER),
    _m('amp', 'Acoustic360', 'Acoustic 360', [('Gain', 0.5), ('Treble', 0.6), ('Middle', 0.4), ('Bass', 0.5), ('Master', 0.7)], OTHER),
    _m('amp', 'GK700RBII', 'GK 700 RB II', [('Gain', 0.5), ('Treble', 0.6), ('Middle', 0.4), ('Bass', 0.5), ('Master', 0.7)], OTHER),
    _m('amp', 'JH.JTM45', 'Marshall JTM45/100', [('Gain', 0.5), ('Treble', 0.6), ('Middle', 0.4), ('Bass', 0.5), ('Master', 0.7)], _FW_1_5),
    _m('amp', 'JH.SuperLead100', 'Marshall Super Lead 100', [('Gain', 1.0), ('Treble', 0.6), ('Middle', 0.4), ('Bass', 0.5), ('Master', 0.7)], _FW_1_5),
    _m('comp', 'JH.Vox846', 'Vox 846 Wah', [('P1', 0.5), ('Mode', 0.0), ('P3', 0.2), ('P4', 0.5), ('P5', 0.5)], _FW_1_5),
    _m('drive', 'MetalZoneMT2', 'Metal Zone MT2', [('Level', 0.8), ('EQ Low', 0.6), ('EQ Middle', 0.19), ('EQ High', 0.37), ('EQ Mid Band', 0.59), ('Distortion', 0.74)], OTHER),
    _m('drive', 'TrebleBooster', 'Treble Booster', [('P3', 0.3), ('P2', 0.8), ('P1', 0.9)], OTHER),
    _m('mod', 'MuTron', 'MuTron III', [('Mode', 0.3), ('Peak', 0.2), ('Depth', 0.9), ('Range', 0.0), ('Position', 0.0)], OTHER),
    _m('mod', 'JH.VoodooVibeJr', 'Voodoo Vibe Junior', [('Speed', 0.2), ('Sweep', 0.5), ('Intensity', 0.7), ('Chorus/Vibrato', 0.5)], _FW_1_5),
    _m("reverb", REVERB, "Reverb", [("Level", 0.5), ("Damping", 0.5), ("Dwell", 0.5), ("Time", 0.5),
                                     ("Low Cut", 0.3), ("High Cut", 0.7), ("Type", 0.0)]),
]

MODELS: dict[str, Model] = {m.id: m for m in _MODELS}


def model(model_id: str) -> Model | None:
    return MODELS.get(model_id)


def display_name(model_id: str, params: list[float] | None = None) -> str:
    """The name the Spark app shows. For reverb, the room picked by its Type parameter."""
    if model_id == REVERB and params and len(params) > REVERB_TYPE_PARAM:
        return REVERB_TYPES[reverb_type_index(params[REVERB_TYPE_PARAM])]
    m = MODELS.get(model_id)
    return m.name if m else model_id


def param_name(model_id: str, index: int) -> str:
    m = MODELS.get(model_id)
    if m and index < len(m.params):
        return m.params[index].name
    return f"Param {index + 1}"


def reverb_type_index(value: float) -> int:
    return max(0, min(len(REVERB_TYPES) - 1, round(value * 10)))


def find(query: str, slot: str | None = None) -> list[Model]:
    """Models whose id or display name matches ``query``: exact matches first, then substrings."""
    q = query.lower().replace(" ", "")
    pool = [m for m in _MODELS if slot is None or m.slot == slot]
    exact = [m for m in pool if q in (m.id.lower().replace(" ", ""), m.name.lower().replace(" ", ""))]
    if exact:
        return exact
    return [m for m in pool if q in m.id.lower().replace(" ", "") or q in m.name.lower().replace(" ", "")]


def for_slot(slot: str, firmware: tuple[int, ...] | None = None) -> list[Model]:
    return [m for m in _MODELS if m.slot == slot and m.supported_by(firmware)]
