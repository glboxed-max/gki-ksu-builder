"""plan / build(dry-run) 的行为测试：不联网、不构建。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kbx.inputs import BuildInputs
from kbx.pipeline import build, pick_tag, plan

ALL = (
    "susfs",
    "kpm",
    "zram_enhanced",
    "zram_full_algos",
    "bbg",
    "ddk_lsm",
    "ntsync",
    "net_enhanced",
    "rekernel",
)


class ValidationTests(unittest.TestCase):
    def test_bad_os_patch_level(self):
        problems = BuildInputs(os_patch_level="2026/07").validate()
        self.assertTrue(any("os_patch_level" in p for p in problems))

    def test_bad_kernel_line(self):
        problems = BuildInputs(android="android14", kernel="7.0").validate()
        self.assertTrue(any("不支持的内核线" in p for p in problems))

    def test_bad_sub_level(self):
        problems = BuildInputs(sub_level="abc").validate()
        self.assertTrue(any("sub_level" in p for p in problems))

    def test_ok(self):
        self.assertEqual(BuildInputs().validate(), [])


class PickTagTests(unittest.TestCase):
    SAMPLE = "\n".join(
        [
            "1111111111111111111111111111111111111111\trefs/tags/android14-6.1.138_r00",
            "2222222222222222222222222222222222222222\trefs/tags/android14-6.1.138_r01",
            "2222222222222222222222222222222222222222\trefs/tags/android14-6.1.138_r01^{}",
            "3333333333333333333333333333333333333333\trefs/tags/android14-6.1.139_r00",
            "4444444444444444444444444444444444444444\trefs/heads/android14-6.1",
        ]
    )

    def test_pick_highest_revision(self):
        self.assertEqual(pick_tag("android14-6.1.138", self.SAMPLE), "android14-6.1.138_r01")

    def test_none_when_missing(self):
        self.assertIsNone(pick_tag("android16-6.12.999", self.SAMPLE))

    def test_ignores_peeled_and_branches(self):
        tag = pick_tag("android14-6.1.139", self.SAMPLE)
        self.assertEqual(tag, "android14-6.1.139_r00")


class PlanTests(unittest.TestCase):
    def test_user_device_plan(self):
        inputs = BuildInputs(
            android="android14",
            kernel="6.1",
            sub_level="138",
            os_patch_level="2026-07",
            ksu="sukisu-13000",
            features=ALL,
        )
        p = plan(inputs)
        text = p.render()
        # 功能闸门
        for name in ("susfs", "kpm", "zram_enhanced", "zram_full_algos", "bbg", "ntsync", "net_enhanced", "rekernel"):
            self.assertIn(name, p.features.active, f"{name} 应当生效")
        self.assertIn("ddk_lsm", p.features.skipped)
        # 管理器配对策略必须写明"不改名"
        self.assertFalse(p.pairing.rename_manager)
        self.assertEqual(p.pairing.manager_apk, "SukiSU-manager-13000.apk")
        # 必须声明按官方文档的集成方式，且不出现文档外的额外改动
        self.assertIn("kernel/setup.sh", p.pairing.pin.docs_flow)
        self.assertIn("不做文档之外的改动", text)
        self.assertNotIn("uapi 兼容补丁", text)
        # 渲染内容包含关键提示
        self.assertIn("不改名、不重签", text)
        self.assertIn("os_version", text)
        self.assertIn("6.12", text)  # zram 自动跳过的说明

    def test_612_plan_skips(self):
        inputs = BuildInputs(android="android16", kernel="6.12", sub_level="X", features=ALL)
        p = plan(inputs)
        self.assertNotIn("susfs", p.features.active)
        self.assertNotIn("zram_enhanced", p.features.active)
        self.assertIn("susfs", p.features.skipped)

    def test_build_dry_run_returns_manifest(self):
        inputs = BuildInputs(android="android14", kernel="6.1", sub_level="138", features=("susfs", "net_enhanced"))
        with tempfile.TemporaryDirectory() as tmp:
            manifest = build(inputs, Path(tmp), dry_run=True)
        self.assertEqual(manifest["inputs"]["kernel"], "6.1")
        self.assertIn("susfs", manifest["features_active"])
        self.assertEqual(manifest["manager"]["apk"], "SukiSU-manager-13000.apk")
        self.assertFalse(manifest["manager"]["renamed"])


if __name__ == "__main__":
    unittest.main()
