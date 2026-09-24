"""SUSFS：内核层隐藏能力。必须使用与 KSU 版本"同代"的补丁栈。"""

from __future__ import annotations

from .. import refs
from . import Feature, FeatureContext


class SusfsFeature(Feature):
    name = "susfs"
    title = "SUSFS"
    status = "verified"

    def _ref(self, ctx: FeatureContext) -> str | None:
        return refs.susfs_ref_for(ctx.line, ctx.pin)

    def applies(self, ctx: FeatureContext) -> tuple[bool, str]:
        if not self._ref(ctx):
            return False, (
                f"{ctx.line.key} 在 SUSFS「同代」时期没有对应的内核补丁"
                "（例如 android16-6.12），为避免与 KSU 侧集成补丁符号不匹配，自动跳过 SUSFS"
            )
        return True, ""

    def describe(self, ctx: FeatureContext) -> list[str]:
        ref = self._ref(ctx)
        return [
            f"clone susfs4ksu @ {ref[:12]}（与内核线同代）",
            "应用内核侧补丁：50_add_susfs_in_<线>.patch",
            "应用 KSU 侧集成补丁：10_enable_susfs_for_ksu.patch（源自带 SUSFS 时跳过）",
            "注入 CONFIG_KSU_SUSFS_* 配置项",
        ]

    def apply(self, ctx: FeatureContext) -> None:
        ref = self._ref(ctx)
        if not ref:
            return
        susfs = ctx.clone(refs.SUSFS_REPO, ref, "susfs4ksu")
        kernel_patch = susfs / f"kernel_patches/50_add_susfs_in_gki-{ctx.line.key}.patch"
        if kernel_patch.is_file():
            ctx.apply_patch(kernel_patch, ctx.src_root)
            ctx.notes.append(f"SUSFS 内核侧补丁已应用: {kernel_patch.name}")
        else:
            ctx.notes.append(f"未找到内核侧补丁 {kernel_patch.name}，需要人工确认路径")
        ksu_patch = susfs / "kernel_patches/10_enable_susfs_for_ksu.patch"
        if ksu_patch.is_file():
            ctx.apply_patch(ksu_patch, ctx.src_root)
            ctx.notes.append("SUSFS KSU 侧集成补丁已应用")
        for key in (
            "CONFIG_KSU_SUSFS",
            "CONFIG_KSU_SUSFS_SUS_PATH",
            "CONFIG_KSU_SUSFS_SUS_MOUNT",
            "CONFIG_KSU_SUSFS_SUS_KSTAT",
            "CONFIG_KSU_SUSFS_SPOOF_UNAME",
        ):
            ctx.inject_config(key, True)
