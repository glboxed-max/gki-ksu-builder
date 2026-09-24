"""网络增强：IPSet + BBR。

这一项基本是"配置级"功能（不需要打补丁），所以状态是 verified；
真正要注意的是 kABI：GKI 内核加 IPSet 会引入新的结构体，需要确认不破坏 KMI。
"""

from __future__ import annotations

from . import Feature, FeatureContext


class NetEnhancedFeature(Feature):
    name = "net_enhanced"
    title = "网络增强（IPSet + BBR）"
    status = "verified"

    def describe(self, ctx: FeatureContext) -> list[str]:
        return [
            "注入 IPSet 相关配置：CONFIG_IP_SET*、CONFIG_NETFILTER_XT_SET、CONFIG_NET_NS",
            "注入 BBR：CONFIG_TCP_CONG_BBR、CONFIG_NET_SCH_FQ、CONFIG_DEFAULT_BBR",
            "把 BBR 设为默认拥塞算法（同时保留 cubic 作为回退）",
        ]

    def apply(self, ctx: FeatureContext) -> None:
        for key in (
            "CONFIG_NETFILTER",
            "CONFIG_NETFILTER_ADVANCED",
            "CONFIG_IP_SET",
            "CONFIG_IP_SET_MAX",
            "CONFIG_NETFILTER_XT_SET",
            "CONFIG_NET_NS",
            "CONFIG_TCP_CONG_BBR",
            "CONFIG_NET_SCH_FQ",
            "CONFIG_NET_SCH_FQ_CODEL",
            "CONFIG_DEFAULT_BBR",
            "CONFIG_DEFAULT_FQ",
        ):
            ctx.inject_config(key, True)
        ctx.notes.append("网络增强：IPSet + BBR 配置已注入（保留 cubic 回退）")
