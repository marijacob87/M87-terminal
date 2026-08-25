import json
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.modules.setdefault("psutil", MagicMock())

from core.status import get_porto_temp


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return json.dumps(
            {"current": {"temperature_2m": 32.4}}
        ).encode("utf-8")


class StatusTests(unittest.TestCase):
    @patch("core.status.urllib.request.urlopen")
    def test_reads_current_temperature_for_porto_coordinates(self, urlopen):
        urlopen.return_value = _Response()

        self.assertEqual(get_porto_temp(), "32°C")
        requested_url = urlopen.call_args.args[0]
        self.assertIn("latitude=41.1579", requested_url)
        self.assertIn("longitude=-8.6291", requested_url)

    @patch("core.status.urllib.request.urlopen", side_effect=OSError)
    def test_returns_placeholder_when_weather_service_fails(self, _urlopen):
        self.assertEqual(get_porto_temp(), "--°C")


if __name__ == "__main__":
    unittest.main()
