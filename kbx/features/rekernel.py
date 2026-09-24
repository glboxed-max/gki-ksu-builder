"""Re-Kernel 驱动（Sakion-Team）。"""

from __future__ import annotations

from .. import refs
from . import Feature, FeatureContext


class ReKernelFeature(Feature):
    name = "rekernel"
    title = "Re-Kernel 驱动"
    status = "verified"

    def describe(self, ctx: FeatureContext) -> list[str]:
        return [
            "clone Re-Kernel（Sakion-Team）",
            "应用其内核侧补丁并按其说明注入配置",
        ]

    def apply(self, ctx: FeatureContext) -> None:
        src = refs.FEATURE_SOURCES["rekernel"]
        repo = ctx.clone(src.repo, src.ref, "rekernel")
        applied = 0
        for patch in sorted(repo.glob("**/*.patch")):
            if "re-kernel" in patch.name.lower() or "rekernel" in patch.name.lower():
                ctx.apply_patch(patch, ctx.src_root)
                applied += 1
        for script in ("setup.sh", "apply.sh"):
            candidate = repo / script
            if candidate.is_file():
                ctx.run(f"sh {candidate}", ctx.src_root)
        ctx.notes.append(f"Re-Kernel: 应用 {applied} 个补丁（自动跟随上游默认分支）")
