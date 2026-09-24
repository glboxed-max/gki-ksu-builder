"""安全类功能：BBG 防格机（Baseband Guard LSM）与 DDK 防格机 LSM。"""

from __future__ import annotations

from .. import refs
from . import Feature, FeatureContext


class BbgFeature(Feature):
    """Baseband Guard：LSM 层保护基带分区，避免被恶意刷写/抹除（俗称"防格机"）。"""

    name = "bbg"
    title = "BBG 防格机（Baseband Guard LSM）"
    status = "verified"

    def applies(self, ctx: FeatureContext) -> tuple[bool, str]:
        if ctx.line.kernel == "5.10":
            return False, "5.10 上 BBG 需要额外的 LSM 回移补丁，暂未验证，自动跳过"
        return True, ""

    def describe(self, ctx: FeatureContext) -> list[str]:
        return [
            "clone Baseband-guard（vc-teahouse）",
            "执行上游 setup.sh，把 LSM 挂进 security/ 子系统",
            "注入 CONFIG_BBG / LSM 相关配置",
        ]

    def apply(self, ctx: FeatureContext) -> None:
        src = refs.FEATURE_SOURCES["baseband_guard"]
        repo = ctx.clone(src.repo, src.ref, "baseband-guard")
        setup = repo / src.extra.get("setup", "setup.sh")
        if setup.is_file():
            ctx.run(f"sh {setup}", ctx.src_root)
            ctx.notes.append("BBG: 已执行上游 setup.sh")
        else:
            ctx.notes.append("BBG: 未找到 setup.sh，需要人工确认上游结构")
        ctx.inject_config("CONFIG_BBG", True)


class DdkLsmFeature(Feature):
    """DDK 防格机 LSM。

    说明：这一项是 ABK 自己的叫法，公开仓库里没有等价的独立补丁源，
    因此本仓库**先标记为 pending 并拒绝启用**，而不是假装它能用。
    """

    name = "ddk_lsm"
    title = "DDK 防格机 LSM"
    status = "pending"

    def applies(self, ctx: FeatureContext) -> tuple[bool, str]:
        return False, (
            "DDK 防格机 LSM 目前只在 ABK 内部集成，公开仓库里没有对应补丁源；"
            "本仓库暂不接入（如需，请提供补丁仓库后写一个 Feature 模块即可）"
        )

    def describe(self, ctx: FeatureContext) -> list[str]:
        return ["（待接入补丁源）"]

    def apply(self, ctx: FeatureContext) -> None:  # pragma: no cover
        raise RuntimeError("ddk_lsm 尚未接入补丁源")
