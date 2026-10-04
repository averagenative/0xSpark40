"""Preset parsing and encoding against presets read from a Spark 40 on firmware 1.2.3.37."""

import tempfile
import unittest
from pathlib import Path

from spark40 import catalog
from spark40 import protocol as p
from spark40.client import parse_event
from spark40.preset import Preset

DATA = Path(__file__).parent / "data"


def captured(name: str) -> bytes:
    decoder = p.Decoder()
    lines = (DATA / f"{name}.hex").read_text().splitlines()
    (message,) = [m for line in lines if line.strip() for m in decoder.feed(bytes.fromhex(line))]
    return message.payload


class PresetTest(unittest.TestCase):
    def test_factory_presets_parse(self):
        names = [Preset.parse(captured(f"preset{n}")).name for n in range(1, 5)]
        self.assertEqual(names, ["1-Clean", "2-Crunch", "3-HighGain", "4-Metal"])

    def test_encode_is_byte_exact(self):
        for name in ("preset1", "preset2", "preset3", "preset4", "current"):
            payload = captured(name)
            preset = Preset.parse(payload)
            self.assertEqual(preset.encode(slot=preset.slot)[1:], payload[1:], name)
            self.assertEqual(preset.checksum, payload[-1])

    def test_chain_order_and_models(self):
        preset = Preset.parse(captured("preset1"))
        self.assertEqual([pd.id for pd in preset.pedals],
                         ["bias.noisegate", "Compressor", "Booster", "Twin", "ChorusAnalog", "DelayMono", "bias.reverb"])
        self.assertEqual(preset.pedal("amp").name, "Black Duo")
        self.assertEqual(preset.pedal("reverb").name, "Hall Natural")
        self.assertFalse(preset.pedal("mod").on)
        self.assertEqual(preset.unsupported((1, 2, 3, 37)), [])

    def test_json_round_trip(self):
        preset = Preset.parse(captured("preset2"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.json"
            preset.save(path)
            loaded = Preset.load(path)
        self.assertEqual(loaded.name, preset.name)
        self.assertEqual(loaded.uuid, preset.uuid)
        self.assertEqual([pd.id for pd in loaded.pedals], [pd.id for pd in preset.pedals])
        for a, b in zip(loaded.pedals, preset.pedals):
            self.assertEqual(a.on, b.on)
            for x, y in zip(a.params, b.params):
                self.assertAlmostEqual(x, y, places=4)

    def test_paul_hamshere_json_form(self):
        data = {"Name": "Old style", "Pedals": [
            {"Name": "bias.noisegate", "OnOff": "Off", "Parameters": [0.5, 0.2]},
            {"Name": "LA2AComp", "OnOff": "On", "Parameters": [0.0, 0.8, 0.3]},
            {"Name": "Booster", "OnOff": "Off", "Parameters": [0.6]},
            {"Name": "Twin", "OnOff": "On", "Parameters": [0.5] * 5},
            {"Name": "ChorusAnalog", "OnOff": "Off", "Parameters": [0.5] * 4},
            {"Name": "DelayMono", "OnOff": "Off", "Parameters": [0.2, 0.2, 0.5, 0.6, 1.0]},
            {"Name": "bias.reverb", "OnOff": "On", "Parameters": [0.5] * 6 + [0.7]}]}
        preset = Preset.from_dict(data)
        self.assertFalse(preset.pedals[0].on)
        self.assertTrue(preset.pedals[1].on)
        self.assertEqual(preset.pedal("reverb").name, "Plate Rich")
        self.assertEqual(Preset.parse(preset.encode()).name, "Old style")

    def test_newer_models_are_flagged(self):
        preset = Preset.parse(captured("preset1"))
        preset.pedals[3].id = "ODS50CN"
        preset.pedals[2].id = "JH.SupaFuzz"
        self.assertEqual(preset.unsupported((1, 2, 3, 37)), ["JH.SupaFuzz", "ODS50CN"])
        self.assertEqual(preset.unsupported((1, 10, 8, 25)), ["JH.SupaFuzz"])  # not in the table


class CatalogTest(unittest.TestCase):
    def test_every_slot_has_models(self):
        for slot in catalog.SLOTS:
            self.assertTrue(catalog.for_slot(slot, (1, 2, 3, 37)), slot)

    def test_find(self):
        self.assertEqual([m.id for m in catalog.find("black duo")], ["Twin"])
        self.assertEqual([m.id for m in catalog.find("plexi", "amp")], ["Plexi"])

    def test_reverb_types(self):
        self.assertEqual(catalog.display_name(catalog.REVERB, [0.5] * 6 + [0.8]), "Plate Long")
        self.assertEqual(catalog.reverb_type_index(0.29999), 3)


class EventTest(unittest.TestCase):
    def test_knob_turned_on_amp(self):
        payload = p.Writer().prefixed_string("Twin").int(0).float(0.75).bytes()
        event = parse_event(p.Message(p.REPLY, p.PARAM_CHANGED, payload))
        self.assertEqual((event.kind, event.effect, event.index, event.value), ("param", "Twin", 0, 0.75))

    def test_preset_button(self):
        event = parse_event(p.Message(p.REPLY, p.SELECT, b"\x00\x02"))
        self.assertEqual((event.kind, event.preset), ("preset", 2))

    def test_unknown_message(self):
        self.assertEqual(parse_event(p.Message(p.REPLY, 0x55, b"\x01")).kind, "other")


if __name__ == "__main__":
    unittest.main()
