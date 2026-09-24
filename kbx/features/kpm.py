"""KPM：KernelSU 的内核模块（可加载扩展）支持。仅 SukiSU 系有。"""

from __future__ import annotations

from . import Feature, FeatureContext


class KpmFeature(Feature):
    name = "kpm"
    title = "KPM 功能"
    status = "verified"

    def applies(self, ctx: FeatureContext) -> tuple[bool, str]:
        if "sukisu" not in ctx.pin.repo.lower():
            return False, f"KPM 仅由 SukiSU 系内核支持，当前 KSU 为 {ctx.pin.display}"
        if ctx.line.kernel in {"5.10", "5.15"}:
            return False, f"{ctx.line.key} 上的 KPM 依赖较多回移补丁，暂未验证，自动跳过"
        return True, ""

    def describe(self, ctx: FeatureContext) -> list[str]:
        return [
            "应用 SukiSU 的 KPM 内核侧改动（kernel/kpm）",
            "注入 CONFIG_KPM=y",
            "记录 KPM 为可失败项：构建失败时降级为警告而不是整体失败",
        ]

    def apply(self, ctx: FeatureContext) -> None:
        ctx.inject_config("CONFIG_KPM", True)
        ctx.notes.append("KPM 已启用（失败时按警告处理，不阻断构建）")
