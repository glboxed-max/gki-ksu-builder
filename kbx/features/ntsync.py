"""NTsync：兼容 Windows NT 内核 API 的高性能同步原语（Wine/Proton 等用）。"""

from __future__ import annotations

from .. import refs
from . import Feature, FeatureContext


class NTsyncFeature(Feature):
    name = "ntsync"
    title = "NTsync"
    status = "pending"

    def applies(self, ctx: FeatureContext) -> tuple[bool, str]:
        if ctx.line.kernel in {"5.10", "5.15"}:
            return False, f"{ctx.line.key} 缺少可用的 NTsync 回移补丁，自动跳过"
        return True, ""

    def describe(self, ctx: FeatureContext) -> list[str]:
        return [
            "clone kernel_patches（NTsync 补丁来源）",
            "应用 NTsync 补丁（drivers/misc/ntsync 或 fs/ 实现）",
            "注入 CONFIG_NTSYNC=y（或上游对应的符号名）",
        ]

    def apply(self, ctx: FeatureContext) -> None:
        src = refs.FEATURE_SOURCES["ntsync"]
        patchdir = ctx.clone(src.repo, src.ref, "kernel_patches")
        applied = 0
        for patch in sorted(patchdir.glob("**/*ntsync*.patch")):
            ctx.apply_patch(patch, ctx.src_root)
            applied += 1
        ctx.inject_config("CONFIG_NTSYNC", True)
        ctx.notes.append(f"NTsync：应用 {applied} 个补丁（状态 pending，需 CI 验证）")
