import unittest

from serial_protocol import make_command, parse_distance


class SerialProtocolTests(unittest.TestCase):
    def test_parses_supported_distance_formats(self):
        self.assertEqual(parse_distance("DIST:25.40 cm"), (25.4, "cm"))
        self.assertEqual(parse_distance("Distance=120mm"), (120.0, "mm"))
        self.assertEqual(parse_distance("距离：1.2米"), (1.2, "m"))
        self.assertEqual(parse_distance("18.5"), (18.5, "cm"))

    def test_rejects_non_distance_message(self):
        self.assertIsNone(parse_distance("START_OK"))

    def test_builds_newline_terminated_command(self):
        self.assertEqual(make_command("id", "20260001"), b"ID:20260001\n")
        self.assertEqual(make_command("start"), b"START\n")


if __name__ == "__main__":
    unittest.main()
