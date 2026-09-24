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
        # 依据：钉住版本官方文档 docs/README.md「KPM 支持」一节
        #   - KPM 源码就在 KSU 源码树的 kernel/kpm/ 里，不需要额外打补丁
        #   - 需要 CONFIG_KPM=y；GKI 默认钩子是 KPROBES，需要 CONFIG_KPROBES=y
        return [
            "确认 kernel/kpm/ 存在（KPM 源码随 KSU 源码一起拉取，无需额外补丁）",
            "注入 CONFIG_KPM=y",
            "注入 CONFIG_KPROBES=y（官方文档：GKI 2.0 默认钩子为 KPROBES）",
        ]

    def apply(self, ctx: FeatureContext) -> None:
        kpm_dir = ctx.src_root / "KernelSU" / "kernel" / "kpm"
        if kpm_dir.is_dir():
            ctx.notes.append("KPM: kernel/kpm/ 存在（随 KSU 源码提供）")
        else:
            ctx.notes.append("KPM: 未找到 kernel/kpm/，请确认 KSU 版本是否包含 KPM")
        ctx.inject_config("CONFIG_KPM", True)
        ctx.inject_config("CONFIG_KPROBES", True)
        ctx.notes.append("KPM 已启用（CONFIG_KPM + CONFIG_KPROBES）")
