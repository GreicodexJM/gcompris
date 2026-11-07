"""Rechazos del empaquetado antes de ejecutar Qt o modificar el paquete."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("pack", Path(__file__).with_name("pack.py"))
pack = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pack)


class PackTests(unittest.TestCase):
    def reject(self, records, state, message):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "elevenlabs").mkdir()
            (root / "ogg/misc").mkdir(parents=True)
            (root / "ogg/misc/welcome.ogg").write_bytes(b"OggSincorrect")
            (root / "manifest.json").write_text(json.dumps({"clips": []}))
            (root / "catalog-elevenlabs.json").write_text(json.dumps({"clips": [
                {"path": "misc/welcome.ogg", "text": "Hola", "status": "ready"}]}))
            (root / "verification.json").write_text(json.dumps({"clips": records}))
            (root / "elevenlabs/state.json").write_text(json.dumps({"clips": {
                "misc/welcome.ogg": state}}))
            with patch.object(pack, "DATA", root), patch.object(pack, "WORK", root), \
                 patch("sys.argv", ["pack", "--elevenlabs", str(root)]), \
                 patch.object(pack.subprocess, "check_output") as external:
                with self.assertRaisesRegex(ValueError, message):
                    pack.main()
                external.assert_not_called()

    def test_missing_conversion_rejected(self):
        self.reject([], {}, "catálogo completo")

    def test_changed_text_rejected(self):
        self.reject([{"path": "misc/welcome.ogg"}],
                    {"status": "completed", "text": "Otro"}, "texto distinto")

    def test_hash_mismatch_rejected(self):
        self.reject([{"path": "misc/welcome.ogg", "bytes": 12, "sha256": "incorrect"}],
                    {"status": "completed", "text": "Hola"}, "Hash")


if __name__ == "__main__":
    unittest.main()
