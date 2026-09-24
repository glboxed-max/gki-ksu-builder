"""ZRAM：增强算法（legacy LZ4K/LZ4KD/LZ4K_OPLUS）与完整算法支持。

这里就是"**6.12 自动跳过**"的实现位置：legacy 算法栈只到 6.6，6.12 上直接跳过并说明原因。
"""

from __future__ import annotations

from .. import refs
from . import Feature, FeatureContext


class ZramEnhancedFeature(Feature):
    """legacy ZRAM 增强算法（来自 SukiSU_patch / kernel_patches）。"""

    name = "zram_enhanced"
    title = "ZRAM 增强算法"
    status = "verified"

    def applies(self, ctx: FeatureContext) -> tuple[bool, str]:
        blocked = refs.blocked_zram_algos(ctx.line)
        if blocked:
            return False, (
                f"{ctx.line.key} 不支持 legacy ZRAM 算法（{'/'.join(blocked)}）："
                "上游补丁栈只到 6.6，自动跳过并保留内核原生算法"
            )
        return True, ""

    def describe(self, ctx: FeatureContext) -> list[str]:
        algos = "、".join(refs.LEGACY_ZRAM_ALGOS)
        return [
            f"clone SukiSU_patch（ZRAM 补丁来源，提供 {algos}）",
            "应用 ZRAM 算法补丁到 mm/zram 与 crypto",
            "注入 CONFIG_CRYPTO_LZ4K / LZ4KD / LZ4K_OPLUS 等配置",
        ]

    def apply(self, ctx: FeatureContext) -> None:
        src = refs.FEATURE_SOURCES["sukisu_patch"]
        patchdir = ctx.clone(src.repo, src.ref, "sukisu_patch")
        zram_dir = patchdir / "other"
        applied = 0
        for patch in sorted(zram_dir.glob("*zram*.patch")) + sorted(zram_dir.glob("*lz4k*.patch")):
            ctx.apply_patch(patch, ctx.src_root)
            applied += 1
        for key in ("CONFIG_CRYPTO_LZ4K", "CONFIG_CRYPTO_LZ4KD", "CONFIG_CRYPTO_LZ4K_OPLUS"):
            ctx.inject_config(key, True)
        ctx.notes.append(f"ZRAM 增强：应用 {applied} 个补丁")


class ZramFullAlgosFeature(Feature):
    """完整算法支持：把用户额外想要的算法写进配置，并对 6.12 过滤 legacy 项。"""

    name = "zram_full_algos"
    title = "ZRAM 完整算法支持（6.12 自动跳过 legacy）"
    status = "verified"

    def applies(self, ctx: FeatureContext) -> tuple[bool, str]:
        return True, ""

    def _algos(self, ctx: FeatureContext) -> tuple[list[str], list[str]]:
        extra = list(ctx.inputs.zram_extra_algos) or list(refs.NATIVE_ZRAM_ALGOS)
        return refs.normalize_zram_algos(ctx.line, extra)

    def describe(self, ctx: FeatureContext) -> list[str]:
        keep, skipped = self._algos(ctx)
        lines = [f"启用 ZRAM 算法：{', '.join(keep) if keep else '(无)'}"]
        if skipped:
            lines.append(
                f"自动跳过（该内核线无补丁）：{', '.join(skipped)} —— 这就是「6.12 自动跳过」逻辑"
            )
        return lines

    def apply(self, ctx: FeatureContext) -> None:
        keep, skipped = self._algos(ctx)
        for algo in keep:
            key = {
                "lzo": "CONFIG_CRYPTO_LZO",
                "lz4": "CONFIG_CRYPTO_LZ4",
                "zstd": "CONFIG_CRYPTO_ZSTD",
                "deflate": "CONFIG_CRYPTO_DEFLATE",
                "842": "CONFIG_CRYPTO_842",
                "lz4hc": "CONFIG_CRYPTO_LZ4HC",
            }.get(algo.lower())
            if key:
                ctx.inject_config(key, True)
        ctx.notes.append(f"ZRAM 算法: 保留 {keep or ['(默认)']}; 跳过 {skipped or ['(无)']}")
