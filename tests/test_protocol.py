"""Framing tests against blocks captured from a Spark 40 on firmware 1.2.3.37."""

import unittest
from pathlib import Path

from spark40 import protocol as p

DATA = Path(__file__).parent / "data"


def blocks(name: str) -> list[bytes]:
    return [bytes.fromhex(line) for line in (DATA / f"{name}.hex").read_text().splitlines() if line.strip()]


class PackingTest(unittest.TestCase):
    def test_round_trip(self):
        data = bytes(range(256)) * 2
        self.assertEqual(p.unpack7(p.pack7(data)), data)
        self.assertTrue(all(b < 0x80 for b in p.pack7(data)))

    def test_short_group(self):
        self.assertEqual(p.pack7(b"\xca\x01\x02"), b"\x01\x4a\x01\x02")
        self.assertEqual(p.unpack7(b"\x01\x4a\x01\x02"), b"\xca\x01\x02")


class EncodeTest(unittest.TestCase):
    def test_get_name_matches_capture(self):
        expected = bytes.fromhex("01fe000053fe17000000000000000000f00100000211f7")
        self.assertEqual(p.encode(p.GET, p.NAME, b"", seq=0), [expected])

    def test_param_change_matches_protocol_notes(self):
        # Paul Hamshere's notes, figure 9: LA2AComp parameter 1 = 0x3f4d42c4
        payload = p.Writer().prefixed_string("LA2AComp").int(1).raw(0xCA, 0x3F, 0x4D, 0x42, 0xC4).bytes()
        (block,) = p.encode(p.SET, p.PARAM, payload, seq=0x32)
        self.assertEqual(block[16:].hex(" "),
                         "f0 01 32 40 01 04 02 08 28 4c 41 32 41 43 10 6f 6d 70 01 4a 3f 4d 02 42 44 f7")
        self.assertEqual(block[6], len(block))

    def test_multi_chunk_split(self):
        payload = bytes(range(200)) + bytes(100)
        out = p.encode(p.SET, p.PRESET, payload, seq=5)
        self.assertEqual(len(out), 3)
        self.assertTrue(all(len(b) <= 0xAD for b in out))
        self.assertEqual(len(out[0]), 0xAD)
        decoder = p.Decoder()
        # Re-label the blocks as coming from the amp so the decoder reassembles them.
        echoed = [b[:4] + p.FROM_AMP + b[6:] for b in out]
        messages = [m for b in echoed for m in decoder.feed(b)]
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].payload, payload)
        self.assertEqual(messages[0].seq, 5)


class DecodeTest(unittest.TestCase):
    def test_preset_reply_reassembles(self):
        decoder = p.Decoder()
        messages = [m for b in blocks("preset3") for m in decoder.feed(b)]
        self.assertEqual([m.key for m in messages], [(p.REPLY, p.PRESET)])
        self.assertIn(b"3-HighGain", messages[0].payload)

    def test_split_notifications(self):
        stream = b"".join(blocks("preset1"))
        decoder = p.Decoder()
        messages = []
        for i in range(0, len(stream), 20):        # a 23-byte MTU splits every block
            messages += decoder.feed(stream[i:i + 20])
        whole = p.Decoder()
        expected = [m for b in blocks("preset1") for m in whole.feed(b)]
        self.assertEqual([m.payload for m in messages], [m.payload for m in expected])

    def test_name_serial_firmware_replies(self):
        decoder = p.Decoder()
        name = decoder.feed(bytes.fromhex("01 fe 00 00 41 ff 23 00 00 00 00 00 00 00 00 00 "
                                          "f0 01 00 5d 03 11 02 08 28 53 70 61 72 6b 00 20 34 30 f7"))
        self.assertEqual(name[0].reader().string(), "Spark 40")
        firmware = decoder.feed(bytes.fromhex("01fe000041ff1d000000000000000000f001026a032f014e01020325f7"))
        self.assertEqual(p.firmware_tuple(firmware[0].reader().int()), (1, 2, 3, 37))

    def test_resyncs_after_garbage(self):
        decoder = p.Decoder()
        reply = bytes.fromhex("01fe000041ff1d000000000000000000f001026a032f014e01020325f7")
        self.assertEqual(len(decoder.feed(b"\x00\x11garbage" + reply)), 1)


class ValuesTest(unittest.TestCase):
    def test_writer_reader_round_trip(self):
        data = (p.Writer().string("Twin").prefixed_string("Booster").long_string("x" * 40)
                .float(0.25).bool(True).bool(False).int(5).int(200).int(0x01020325).array(3).bytes())
        r = p.Reader(data)
        self.assertEqual(r.string(), "Twin")
        self.assertEqual(r.string(), "Booster")
        self.assertEqual(r.string(), "x" * 40)
        self.assertEqual(r.float(), 0.25)
        self.assertTrue(r.bool())
        self.assertFalse(r.bool())
        self.assertEqual((r.int(), r.int(), r.int()), (5, 200, 0x01020325))
        self.assertEqual(r.array(), 3)
        self.assertEqual(r.remaining(), 0)

    def test_reader_rejects_wrong_type(self):
        with self.assertRaises(p.ProtocolError):
            p.Reader(b"\xc3").float()


if __name__ == "__main__":
    unittest.main()
