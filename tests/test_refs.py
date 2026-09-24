"""固定表与能力闸门的单元测试（本地秒级，不联网）。"""

from __future__ import annotations

import re
import unittest

from kbx import refs


class KernelLineTests(unittest.TestCase):
    def test_lines_complete(self):
        expected = {"android12-5.10", "android13-5.15", "android14-6.1", "android15-6.6", "android16-6.12"}
        self.assertEqual(set(refs.KERNEL_LINES), expected)

    def test_lookup_and_error(self):
        line = refs.kernel_line("android14", "6.1")
        self.assertEqual(line.key, "android14-6.1")
        self.assertFalse(line.is_612)
        self.assertTrue(refs.kernel_line("android16", "6.12").is_612)
        with self.assertRaises(refs.RefError):
            refs.kernel_line("android99", "9.9")


class KsuPinTests(unittest.TestCase):
    def test_pins_have_refs(self):
        for key, pin in refs.KSU_PINS.items():
            with self.subTest(pin=key):
                self.assertTrue(pin.ref, f"{key} 缺少 ref")
                self.assertTrue(pin.repo)
                self.assertTrue(pin.display)

    def test_13000_pairing(self):
        pin = refs.ksu_pin("sukisu-13000")
        self.assertEqual(pin.driver_version_code, 13000)
        self.assertEqual(pin.manager_version_code, 13000)
        self.assertTrue(pin.legacy_uapi, "13000 属于 legacy uapi，必须给 ksud 打补丁")
        self.assertEqual(pin.manager_apk, "SukiSU-manager-13000.apk")

    def test_unknown_pin(self):
        with self.assertRaises(refs.RefError):
            refs.ksu_pin("不存在的版本")


class SusfsPinTests(unittest.TestCase):
    def test_same_era_refs_are_hashes(self):
        for key, ref in refs.SUSFS_SAME_ERA.items():
            with self.subTest(line=key):
                if ref is None:
                    self.assertEqual(key, "android16-6.12", "只有 6.12 允许没有同代补丁")
                else:
                    self.assertRegex(ref, r"^[0-9a-f]{40}$")

    def test_612_has_no_susfs(self):
        line = refs.kernel_line("android16", "6.12")
        self.assertIsNone(refs.susfs_ref_for(line, refs.ksu_pin("sukisu-13000")))

    def test_pin_susfs_takes_priority(self):
        line = refs.kernel_line("android14", "6.1")
        pin = refs.ksu_pin("sukisu-13000")
        self.assertEqual(refs.susfs_ref_for(line, pin), pin.susfs_ref)


class ZramGateTests(unittest.TestCase):
    def test_612_blocks_legacy_algos(self):
        line = refs.kernel_line("android16", "6.12")
        blocked = refs.blocked_zram_algos(line)
        self.assertIn("lz4k", blocked)
        keep, skipped = refs.normalize_zram_algos(line, ["lz4k", "lz4kd", "lzo", "zstd"])
        self.assertEqual(keep, ["lzo", "zstd"])
        self.assertEqual(skipped, ["lz4k", "lz4kd"])

    def test_61_keeps_legacy_algos(self):
        line = refs.kernel_line("android14", "6.1")
        keep, skipped = refs.normalize_zram_algos(line, ["lz4k", "lzo"])
        self.assertEqual(keep, ["lz4k", "lzo"])
        self.assertEqual(skipped, [])


class FeatureSourceTests(unittest.TestCase):
    def test_sources_have_repo_and_status(self):
        for name, src in refs.FEATURE_SOURCES.items():
            with self.subTest(feature=name):
                self.assertTrue(src.repo.startswith("http"))
                self.assertIn(src.status, {"verified", "pending"})

    def test_manager_rename_is_forbidden(self):
        self.assertFalse(refs.MANAGER_RENAME, "本仓库不允许重命名/重签管理器")


if __name__ == "__main__":
    unittest.main()
