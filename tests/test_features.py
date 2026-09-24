"""功能闸门与依赖解析的单元测试。"""

from __future__ import annotations

import unittest
from pathlib import Path

from kbx.features import REGISTRY, Feature, FeatureContext, resolve
from kbx.inputs import BuildInputs


def ctx(android: str, kernel: str, ksu: str = "sukisu-13000", features: tuple[str, ...] = ()) -> FeatureContext:
    inputs = BuildInputs(android=android, kernel=kernel, ksu=ksu, features=features)
    return FeatureContext(
        inputs=inputs,
        line=inputs.line,
        pin=inputs.pin,
        src_root=Path("/tmp/kernel"),
        work=Path("/tmp/work"),
        clone=lambda repo, ref, name: Path("/tmp/work") / name,
        apply_patch=lambda patch, root: None,
        inject_config=lambda key, enable=True: None,
        run=lambda cmd, cwd: None,
    )


class ResolveTests(unittest.TestCase):
    def test_unknown_feature_raises(self):
        with self.assertRaises(KeyError):
            resolve(["不存在的功能"], ctx("android14", "6.1"))

    def test_612_skips_susfs_and_zram_enhanced(self):
        r = resolve(["susfs", "zram_enhanced", "zram_full_algos"], ctx("android16", "6.12"))
        self.assertIn("zram_full_algos", r.active)
        self.assertNotIn("susfs", r.active)
        self.assertNotIn("zram_enhanced", r.active)
        self.assertIn("SUSFS", r.skipped["susfs"])
        self.assertIn("6.12", r.skipped["zram_enhanced"])

    def test_61_keeps_everything_supported(self):
        want = ("susfs", "kpm", "zram_enhanced", "zram_full_algos", "bbg", "ntsync", "net_enhanced", "rekernel")
        r = resolve(want, ctx("android14", "6.1", features=want))
        self.assertEqual(set(r.active), set(want))

    def test_ddk_lsm_is_pending_and_skipped(self):
        r = resolve(["ddk_lsm"], ctx("android14", "6.1"))
        self.assertEqual(r.active, [])
        self.assertIn("ddk_lsm", r.skipped)
        self.assertIn("没有对应补丁源", r.skipped["ddk_lsm"])

    def test_kpm_requires_sukisu(self):
        r = resolve(["kpm"], ctx("android14", "6.1", ksu="official-stable"))
        self.assertEqual(r.active, [])
        self.assertIn("SukiSU", r.skipped["kpm"])

    def test_510_skips_bbg_and_ntsync(self):
        r = resolve(["bbg", "ntsync"], ctx("android12", "5.10"))
        self.assertEqual(r.active, [])
        self.assertIn("bbg", r.skipped)
        self.assertIn("ntsync", r.skipped)

    def test_missing_dependency_chain(self):
        """依赖解析：前置功能被跳过时，依赖它的功能要连带跳过并说明原因。"""

        class NeedsSusfs(Feature):
            name = "needs_susfs"
            title = "测试用功能"
            requires = ("susfs",)

        REGISTRY["needs_susfs"] = NeedsSusfs()
        try:
            r = resolve(["susfs", "needs_susfs"], ctx("android16", "6.12"))
            self.assertNotIn("susfs", r.active)
            self.assertNotIn("needs_susfs", r.active)
            self.assertIn("前置功能", r.skipped["needs_susfs"])
        finally:
            REGISTRY.pop("needs_susfs", None)

    def test_dependency_missing_entirely(self):
        class NeedsMissing(Feature):
            name = "needs_missing"
            title = "测试用功能"
            requires = ("susfs",)

        REGISTRY["needs_missing"] = NeedsMissing()
        try:
            r = resolve(["needs_missing"], ctx("android14", "6.1"))
            self.assertEqual(r.active, [])
            self.assertIn("缺少前置功能", r.skipped["needs_missing"])
        finally:
            REGISTRY.pop("needs_missing", None)


if __name__ == "__main__":
    unittest.main()
