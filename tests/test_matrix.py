"""矩阵生成脚本的测试（CI 与本地跑的是同一份逻辑）。"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "gen_matrix.py"


def run(*args: str) -> str:
    out = subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


class GenMatrixTests(unittest.TestCase):
    def test_without_612(self):
        raw = run("--with-612", "false")
        self.assertTrue(raw.startswith("matrix="))
        data = json.loads(raw.split("=", 1)[1])
        lines = [item["line"] for item in data["include"]]
        self.assertEqual(lines, ["android12-5.10", "android13-5.15", "android14-6.1", "android15-6.6"])
        self.assertNotIn("android16-6.12", lines)

    def test_with_612(self):
        data = json.loads(run("--with-612", "true", "--format", "json"))
        lines = [item["line"] for item in data["include"]]
        self.assertIn("android16-6.12", lines)

    def test_each_item_has_fields_required_by_workflow(self):
        data = json.loads(run("--with-612", "true", "--format", "json"))
        for item in data["include"]:
            self.assertEqual({"android", "kernel", "sub_level", "line"}, set(item))


if __name__ == "__main__":
    unittest.main()
