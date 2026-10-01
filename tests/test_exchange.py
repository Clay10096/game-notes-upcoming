import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from common import SourceError
from exchange import parse_rates, refresh
from check_site import validate_status


class ExchangeTests(unittest.TestCase):
    xml = '''<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref"><Cube><Cube time="2026-09-28"><Cube currency="USD" rate="1.1"/><Cube currency="HKD" rate="8.5"/><Cube currency="JPY" rate="160"/><Cube currency="CNY" rate="8"/></Cube></Cube></gesmes:Envelope>'''

    def test_ecb_conversion_and_incomplete_quote_rejection(self):
        quoted, rates = parse_rates(self.xml)
        self.assertEqual(quoted, "2026-09-28")
        self.assertAlmostEqual(rates["JPY"], .05)
        self.assertAlmostEqual(rates["USD"], 8 / 1.1)
        for raw in (self.xml.replace('<Cube currency="CNY" rate="8"/>', ''),
                    self.xml.replace('rate="8"', 'rate="NaN"'),
                    self.xml.replace('2026-09-28', '2099-09-28')):
            with self.assertRaises(SourceError):
                parse_rates(raw)

    def test_failed_quote_keeps_prior_valid_rates(self):
        class FixtureClient:
            raw = ExchangeTests.xml
            def request(self, *args, **kwargs):
                return self.raw
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            client = FixtureClient()
            snapshot = refresh(directory, client)
            before = (directory / "fx.json").read_bytes()
            client.raw = "upstream unavailable"
            with self.assertRaises(SourceError):
                refresh(directory, client)
            self.assertEqual(before, (directory / "fx.json").read_bytes())
            validate_status(json.loads((directory / "fx.status.json").read_text()), snapshot)


if __name__ == "__main__":
    unittest.main()
