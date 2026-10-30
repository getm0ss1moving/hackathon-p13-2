"""仅合成文件验证官方哈希门禁；不导入官方入口、不读任何题库。"""

import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check_official_integrity as integrity


class OfficialIntegrityTests(unittest.TestCase):
    def test_changed_or_missing_official_file_stops_verification(self):
        data = b"synthetic original script\n"
        expected = {"implementation/scorer.py": hashlib.sha256(data).hexdigest()}
        with tempfile.TemporaryDirectory() as directory, patch.object(integrity, "OFFICIAL_SHA256", expected):
            root = Path(directory)
            path = root / "implementation/scorer.py"
            path.parent.mkdir()
            with self.assertRaises(ValueError):
                integrity.require_official_files(root)
            path.write_bytes(data)
            self.assertTrue(integrity.require_official_files(root)["unchanged"])
            path.write_bytes(data + b"# changed\n")
            with self.assertRaisesRegex(ValueError, "scorer.py"):
                integrity.require_official_files(root)

    def test_verification_never_executes_official_script(self):
        data = b"raise RuntimeError('must not execute')\n"
        expected = {"implementation/eval.py": hashlib.sha256(data).hexdigest()}
        with tempfile.TemporaryDirectory() as directory, patch.object(integrity, "OFFICIAL_SHA256", expected):
            root = Path(directory)
            path = root / "implementation/eval.py"
            path.parent.mkdir()
            path.write_bytes(data)
            report = integrity.require_official_files(root)
            self.assertEqual(report["scripts_executed"], False)
            self.assertEqual(report["model_requests"], 0)
