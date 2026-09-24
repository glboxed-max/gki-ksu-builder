"""版本与来源固定表。

本文件是整套构建的"事实来源"：任何仓库地址、提交、版本号都只在这里定义，
其它模块通过查询函数取值，避免出现"YAML 里写一份、脚本里写一份"的漂移。

数据来自对既有构建（ABK 系）的核对，以及各上游仓库的实际 README/发布物。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

FeatureStatus = Literal["verified", "pending"]


class RefError(RuntimeError):
    """固定表查询失败（未知内核线 / 未知 KSU 版本 / 缺少同代补丁）。"""


#: 固定表里的仓库可以用 owner/name 简写，统一在这里补全
GITHUB = "https://github.com/"


# --------------------------------------------------------------------------- #
# 内核线
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class KernelLine:
    key: str  # android14-6.1
    android: str  # android14
    kernel: str  # 6.1
    kmi: str  # KMI 标识（用于 ZRAM/ABI 判断）
    aosp_branch: str  # kernel/common 分支

    @property
    def is_612(self) -> bool:
        return self.kernel == "6.12"


KERNEL_LINES: dict[str, KernelLine] = {
    "android12-5.10": KernelLine("android12-5.10", "android12", "5.10", "android12-5.10", "android12-5.10"),
    "android13-5.15": KernelLine("android13-5.15", "android13", "5.15", "android13-5.15", "android13-5.15"),
    "android14-6.1": KernelLine("android14-6.1", "android14", "6.1", "android14-6.1", "android14-6.1"),
    "android15-6.6": KernelLine("android15-6.6", "android15", "6.6", "android15-6.6", "android15-6.6"),
    "android16-6.12": KernelLine("android16-6.12", "android16", "6.12", "android16-6.12", "android16-6.12"),
}


def kernel_line(android: str, kernel: str) -> KernelLine:
    key = f"{android}-{kernel}"
    try:
        return KERNEL_LINES[key]
    except KeyError:
        known = ", ".join(sorted(KERNEL_LINES))
        raise RefError(f"不支持的内核线 {key}（可用：{known}）") from None


# --------------------------------------------------------------------------- #
# KernelSU 版本固定
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class KsuPin:
    key: str  # sukisu-13000
    repo: str  # 上游仓库
    ref: str  # 提交 / tag
    display: str  # 选择器里显示的名字
    driver_version_code: int  # 内核侧驱动版本号（写进源码）
    manager_version_code: int  # 配套管理器 APK 的版本号
    legacy_uapi: bool = False  # 仅为记录：该版本驱动属于早期（uapi 概念前）实现
    susfs_ref: str | None = None  # 与之内核侧同代的 susfs4ksu 提交
    note: str = ""
    #: 官方文档里给出的集成方式（本仓库严格按它执行，不额外发明步骤）
    docs_flow: str = (
        "内核源码根目录执行 kernel/setup.sh <该提交>（官方 docs/README.md「如何添加」一节）"
    )

    @property
    def manager_apk(self) -> str:
        return f"SukiSU-manager-{self.manager_version_code}.apk"

    @property
    def repo_url(self) -> str:
        """可直接交给 git clone 的地址（固定表里写的是 owner/name 简写）。"""
        if self.repo.startswith(("http://", "https://", "git@")):
            return self.repo
        return GITHUB + self.repo


KSU_PINS: dict[str, KsuPin] = {
    "sukisu-13000": KsuPin(
        key="sukisu-13000",
        repo="SukiSU-Ultra/SukiSU-Ultra",
        ref="fa060dca587b6395ac6f80173a121da395676f15",
        display="SukiSU 3.1.5(13000)",
        driver_version_code=13000,
        manager_version_code=13000,
        legacy_uapi=True,
        susfs_ref="b5c3ada461a61c6ad033693b7a00494ead3a28fd",
        note="钉住的 3.x 正式版：驱动报 uapi=0，必须配打过补丁的 ksud",
    ),
    "sukisu-12807": KsuPin(
        key="sukisu-12807",
        repo="SukiSU-Ultra/SukiSU-Ultra",
        ref="9919d573fe1580c638904a866a2ebe44fafef55f",
        display="SukiSU 3.0(12807)",
        driver_version_code=12800,
        manager_version_code=12807,
        legacy_uapi=True,
        susfs_ref="b5c3ada461a61c6ad033693b7a00494ead3a28fd",
        note="更早的 3.x 正式版，同样属于 legacy uapi",
    ),
    "sukisu-stable": KsuPin(
        key="sukisu-stable",
        repo="SukiSU-Ultra/SukiSU-Ultra",
        ref="278d822a4ebd214bcfd774b7910cb11cdc560bb9",
        display="SukiSU(Stable)",
        driver_version_code=0,  # 0 = 不强制改写版本号
        manager_version_code=0,
        note="不 pin 版本号，用源码自带",
    ),
    "official-stable": KsuPin(
        key="official-stable",
        repo="tiann/KernelSU",
        ref="e6832ed548ada2fa16fcbd6c8e98bbd1868f4401",
        display="KernelSU 官方(Stable)",
        driver_version_code=0,
        manager_version_code=0,
        note="官方 v1.0 起只支持 GKI；不含 KPM",
    ),
    "next-stable": KsuPin(
        key="next-stable",
        repo="KernelSU-Next/KernelSU-Next",
        ref="d3c68954a46d3c8961d6c83d55e5f6638d593482",
        display="KernelSU-Next(Stable)",
        driver_version_code=0,
        manager_version_code=0,
        note="GKI 用 dev/stable 分支",
    ),
    "resukisu-stable": KsuPin(
        key="resukisu-stable",
        repo="ReSukiSU/ReSukiSU",
        ref="2206a7dd71e600f34378c4c583244f46e7a35670",
        display="ReSukiSU(Stable)",
        driver_version_code=0,
        manager_version_code=0,
        note="SukiSU 的再分支，主打旧内核/多管理器",
    ),
}


def ksu_pin(key: str) -> KsuPin:
    try:
        return KSU_PINS[key]
    except KeyError:
        known = ", ".join(sorted(KSU_PINS))
        raise RefError(f"未知的 KSU 版本 {key}（可用：{known}）") from None


# --------------------------------------------------------------------------- #
# SUSFS：按内核线选"同代"补丁（必须与 KSU 侧集成补丁同一时期）
# --------------------------------------------------------------------------- #
SUSFS_REPO = "https://gitlab.com/simonpunk/susfs4ksu.git"
SUSFS_SAME_ERA: dict[str, str | None] = {
    "android12-5.10": "5a3153f9f8b18ed81628d9cc33726f52e5a5f5c6",
    "android13-5.15": "b54390da29cb9d414bbc4c58032c62d146b89990",
    "android14-6.1": "b5c3ada461a61c6ad033693b7a00494ead3a28fd",
    "android15-6.6": "09fec8aa1f39807788c526dd84429f6d92b805ae",
    "android16-6.12": None,  # 该时期没有 6.12 内核补丁 -> 自动关闭 SUSFS
}


def susfs_ref_for(line: KernelLine, pin: KsuPin | None) -> str | None:
    """取该内核线可用的同代 SUSFS 提交。

    注意顺序：**内核线是否具备同代补丁是硬前提**。某条线（如 6.12）在 SUSFS
    同代时期根本没有对应内核补丁，这时无论 KSU 版本自带什么提交都不能启用 SUSFS，
    否则会出现"内核侧补丁缺失、KSU 侧补丁符号对不上"的构建失败。
    """
    if SUSFS_SAME_ERA.get(line.key) is None:
        return None
    if pin is not None and pin.susfs_ref:
        return pin.susfs_ref
    return SUSFS_SAME_ERA.get(line.key)


# --------------------------------------------------------------------------- #
# 附加功能来源
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FeatureSource:
    repo: str  # clone 用的地址
    ref: str | None = None  # None = 跟随默认分支
    status: FeatureStatus = "pending"
    note: str = ""
    extra: dict[str, str] = field(default_factory=dict)


FEATURE_SOURCES: dict[str, FeatureSource] = {
    "kernel_patches": FeatureSource(
        "https://github.com/WildKernels/kernel_patches.git",
        status="verified",
        note="通用内核补丁合集（ZRAM 算法、网络等）",
    ),
    "sukisu_patch": FeatureSource(
        "https://github.com/ShirkNeko/SukiSU_patch.git",
        status="verified",
        note="SukiSU 附加补丁（LZ4KD / ZRAM / 网络等）",
    ),
    "baseband_guard": FeatureSource(
        "https://github.com/vc-teahouse/Baseband-guard.git",
        status="verified",
        note="BBG 防格机：LSM 层保护基带分区",
        extra={"setup": "setup.sh"},
    ),
    "rekernel": FeatureSource(
        "https://github.com/Sakion-Team/Re-Kernel.git",
        status="verified",
        note="Re-Kernel 驱动",
    ),
    "ntsync": FeatureSource(
        "https://github.com/WildKernels/kernel_patches.git",
        status="pending",
        note="NTsync 补丁（待在各内核线逐条验证）",
    ),
}

#: ZRAM 增强算法里"旧版补丁栈"提供的算法，6.12 无对应补丁 -> 自动跳过
LEGACY_ZRAM_ALGOS = ("lz4k", "lz4kd", "lz4k_oplus")
#: 内核原生即可用的算法（任何线都可开）
NATIVE_ZRAM_ALGOS = ("lzo", "lzo-rle", "lz4", "zstd", "deflate", "842", "lz4hc")


def blocked_zram_algos(line: KernelLine) -> tuple[str, ...]:
    """该内核线上不能启用的 legacy ZRAM 算法。"""
    return LEGACY_ZRAM_ALGOS if line.is_612 else ()


def normalize_zram_algos(line: KernelLine, extra: list[str]) -> tuple[list[str], list[str]]:
    """返回 (保留的算法, 被跳过的算法)。"""
    blocked = set(blocked_zram_algos(line))
    keep = [a for a in extra if a.lower() not in blocked]
    skipped = [a for a in extra if a.lower() in blocked]
    return keep, skipped


# --------------------------------------------------------------------------- #
# 管理器配对
# --------------------------------------------------------------------------- #
#: 管理器一律使用上游原版：**不改包名、不重签**。
#: 原因：内核按"签名证书"信任管理器，重签会让内核白名单与管理器对不上，
#: 并且"管理器身份"在同一时刻只能属于一个 App，重签后极易陷入死锁。
MANAGER_RENAME = False

#: 旧版驱动（legacy uapi）必须替换 ksud，否则管理器/ksud 会判定版本不匹配
KSUD_UAPI_PATCH_MARKER = "kbx legacy uapi compatibility"
