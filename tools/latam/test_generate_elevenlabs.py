"""Pruebas sin red ni gasto: python3 -m unittest discover -s tools/latam -p 'test_*.py'."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

SPEC = importlib.util.spec_from_file_location("generator", Path(__file__).with_name("generate_elevenlabs.py"))
generator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generator)


class Response(io.BytesIO):
    def __init__(self, data, headers=None):
        super().__init__(data)
        self.headers = headers or {}


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.work = self.root / "work"
        self.data.mkdir()
        self.catalog = {"model": "eleven_multilingual_v2", "clips": [
            {"path": "misc/welcome.ogg", "text": "Hola", "status": "ready", "voice": "jessica"},
            {"path": "alphabet/U006D.ogg", "text": "", "status": "needs_phoneme_review", "voice": "jessica"}]}
        self.save_catalog()

    def tearDown(self):
        self.temp.cleanup()

    def save_catalog(self):
        (self.data / "catalog-elevenlabs.json").write_text(json.dumps(self.catalog))

    def run_generator(self, args, network):
        with patch.object(generator, "DATA", self.data), patch.object(generator, "WORK", self.work), \
             patch.object(generator, "key", return_value="not-a-real-key"), \
             patch.object(generator.urllib.request, "urlopen", side_effect=network) as calls, \
             patch("sys.argv", ["generate", *args]), contextlib.redirect_stdout(io.StringIO()):
            generator.main()
        return calls

    def voices(self):
        return Response(json.dumps({"voices": [{"voice_id": generator.VOICES["jessica"], "category": "premade"}]}).encode())

    def state(self):
        return json.loads((self.work / "state.json").read_text())

    def test_dry_run_never_uses_network(self):
        calls = self.run_generator([], AssertionError("No debe llamar a red"))
        calls.assert_not_called()

    def test_success_then_resume_does_not_regenerate(self):
        calls = self.run_generator(["--run"], [self.voices(), Response(b"ID3" + b"x" * 200,
                                  {"Content-Type": "audio/mpeg", "character-cost": "4"})])
        self.assertEqual(calls.call_count, 2)
        self.assertEqual(self.state()["reserved_characters"], 4)
        self.assertEqual(self.state()["clips"]["misc/welcome.ogg"]["status"], "completed")
        self.assertTrue((self.work / "mp3/misc/welcome.mp3").exists())
        calls = self.run_generator(["--run"], [self.voices()])
        self.assertEqual(calls.call_count, 1)  # Solo consultar voces; ningún POST.

    def test_budget_stops_before_post(self):
        calls = self.run_generator(["--run", "--max-characters", "3"], [self.voices()])
        self.assertEqual(calls.call_count, 1)
        self.assertFalse((self.work / "state.json").exists())

    def test_paid_voice_is_rejected_locally(self):
        voices = Response(json.dumps({"voices": [{"voice_id": generator.VOICES["jessica"],
                                                "category": "professional"}]}).encode())
        with self.assertRaises(SystemExit):
            self.run_generator(["--run"], [voices])
        self.assertFalse((self.work / "state.json").exists())

    def test_quota_error_no_retry(self):
        error = urllib.error.HTTPError("https://example.invalid", 402, "Payment", {},
                     io.BytesIO(b'{"detail":{"status":"quota_exceeded"}}'))
        calls = self.run_generator(["--run"], [self.voices(), error])
        self.assertEqual(calls.call_count, 2)
        item = self.state()["clips"]["misc/welcome.ogg"]
        self.assertEqual(item["status"], "rejected")
        self.assertEqual(item["http_status"], 402)

    def test_timeout_marks_unknown_and_does_not_retry(self):
        calls = self.run_generator(["--run"], [self.voices(), TimeoutError()])
        self.assertEqual(calls.call_count, 2)
        self.assertEqual(self.state()["clips"]["misc/welcome.ogg"]["status"], "unknown_outcome")
        calls = self.run_generator(["--run"], [self.voices()])
        self.assertEqual(calls.call_count, 1)


if __name__ == "__main__":
    unittest.main()
