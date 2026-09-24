"""管理器配对的单元测试：ksud uapi 补丁与驱动版本号固定。

这两件事决定"管理器能不能认到内核"，是最该有测试覆盖的地方：
* 上游不同版本的 ksud 文件结构差别很大，必须都能正确处理；
* 只有"找到了却改不动"才算异常，找不到目标函数要按"无需补丁"处理（记进 manifest）。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kbx.manager import (
    KSUD_ORIGINAL,
    KSUD_PATCHED,
    KSUD_UAPI_PATCH_MARKER,
    patch_ksud,
    pin_driver_version,
    pairing,
)
from kbx.refs import ksu_pin


class KsudPatchTests(unittest.TestCase):
    def _write(self, root: Path, rel: str, text: str) -> Path:
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
        return f

    def test_patches_expected_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            f = self._write(root, "userspace/ksud/src/ksucalls.rs", KSUD_ORIGINAL)
            self.assertEqual(patch_ksud(root), "patched")
            self.assertIn(KSUD_UAPI_PATCH_MARKER, f.read_text(encoding="utf-8"))

    def test_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "userspace/ksud/src/ksucalls.rs", KSUD_PATCHED)
            self.assertEqual(patch_ksud(root), "already")

    def test_finds_implementation_in_other_file(self):
        """上游把实现拆到子模块时，也要能递归找到。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            f = self._write(root, "userspace/ksud/src/ksucalls/linux.rs", KSUD_ORIGINAL)
            self.assertEqual(patch_ksud(root), "patched")
            self.assertIn(KSUD_UAPI_PATCH_MARKER, f.read_text(encoding="utf-8"))

    def test_not_found_is_not_an_error(self):
        """钉住的 3.x 版本没有 uapi 检查 —— 应当返回 not-found 而不是抛异常。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "userspace/ksud/src/ksucalls.rs", "pub fn get_version() -> i32 { 0 }\n")
            self.assertEqual(patch_ksud(root), "not-found")

    def test_missing_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(patch_ksud(Path(tmp)), "not-found")


class DriverVersionTests(unittest.TestCase):
    def test_pins_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            f = root / "kernel" / "KernelSU.h"
            f.parent.mkdir(parents=True)
            f.write_text("#define KERNEL_SU_VERSION 99\n", encoding="utf-8")
            status = pin_driver_version(root, 13000)
            self.assertTrue(status.startswith("pinned:"))
            self.assertIn("13000", f.read_text(encoding="utf-8"))

    def test_already_pinned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            f = root / "kernel" / "ksu.h"
            f.parent.mkdir(parents=True)
            f.write_text("#define KERNEL_SU_VERSION 13000\n", encoding="utf-8")
            self.assertTrue(pin_driver_version(root, 13000).startswith("already:"))

    def test_zero_means_skip(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(pin_driver_version(Path(tmp), 0), "skipped")

    def test_not_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(pin_driver_version(Path(tmp), 13000), "not-found")


class PairingPolicyTests(unittest.TestCase):
    def test_never_renames_manager(self):
        report = pairing(ksu_pin("sukisu-13000"))
        self.assertFalse(report.rename_manager)
        self.assertEqual(report.manager_apk, "SukiSU-manager-13000.apk")
        text = "\n".join(report.lines())
        self.assertIn("不改名、不重签", text)
        # 必须体现"按官方文档集成"
        self.assertIn("kernel/setup.sh", text)
        # 设备侧提醒：先卸干净旧管理器，避免残留 ksud 造成版本不匹配
        self.assertTrue(any("卸载" in n for n in report.device_notes))

    def test_report_does_not_mention_patching_ksud(self):
        """官方文档没有这一步，报告里也不应出现。"""
        text = "\n".join(pairing(ksu_pin("sukisu-13000")).lines())
        self.assertNotIn("给 ksud", text)


if __name__ == "__main__":
    unittest.main()
