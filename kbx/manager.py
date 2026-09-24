"""管理器配对：本仓库**唯一的立场**是"不改名、不重签"。

背景（为什么必须这样）：
* 内核按**签名证书**信任管理器，同时"管理器身份"在同一时刻**只属于一个 App**；
* 一旦为了换包名去重签管理器，内核里写的证书摘要就与管理器对不上，
  于是出现"驱动在跑、管理器却显示未安装"的死锁（旧方案踩过）；
* 正确做法是：内核信任上游证书 + 使用**与驱动同代**的上游管理器 APK。

另外，钉住的旧版 KSU（如 13000）驱动会报告 `uapi=0`，而配套 ksud 期望非 0，
因此这里会在构建时给 **ksud 源码**打一个兼容补丁（只改 ksud，内核不动）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import refs
from .refs import KSUD_UAPI_PATCH_MARKER, KsuPin

KSUD_FILE = Path("userspace/ksud/src/ksucalls.rs")

_ORIGINAL = """pub fn ensure_uapi_version_matched() -> anyhow::Result<()> {
    let kernel_uapi = get_info().uapi_version;
    let userspace_uapi = uapi_version();
    if kernel_uapi != userspace_uapi {
        bail!(
            "UAPI version mismatch: kernel={kernel_uapi}, ksud={userspace_uapi}. Please update KernelSU!"
        );
    }
    Ok(())
}
"""

_PATCHED = f"""pub fn ensure_uapi_version_matched() -> anyhow::Result<()> {{
    let kernel_uapi = get_info().uapi_version;
    let userspace_uapi = uapi_version();
    if kernel_uapi == 0 {{
        // {KSUD_UAPI_PATCH_MARKER}:
        // 钉住的旧版驱动不提供 uapi（报告 0），此时不阻断，直接沿用 userspace 的 uapi。
        eprintln!(
            "[kbx] legacy kernel uapi=0, continue with userspace uapi={{userspace_uapi}}"
        );
        return Ok(());
    }}
    if kernel_uapi != userspace_uapi {{
        bail!(
            "UAPI version mismatch: kernel={{kernel_uapi}}, ksud={{userspace_uapi}}. Please update KernelSU!"
        );
    }}
    Ok(())
}}
"""


@dataclass
class PairingReport:
    """构建时打印并写进 manifest，明确管理器怎么配。"""

    pin: KsuPin
    manager_apk: str
    rename_manager: bool
    ksud_patch_needed: bool
    steps: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        return [
            f"KSU 版本      : {self.pin.display}（驱动版本号 {self.pin.driver_version_code or '源码自带'}）",
            f"配套管理器    : {self.manager_apk}（**上游原版，不改名、不重签**）",
            f"ksud uapi 补丁: {'需要（旧版驱动 uapi=0）' if self.ksud_patch_needed else '不需要'}",
            *[f"  · {s}" for s in self.steps],
        ]


def pairing(pin: KsuPin) -> PairingReport:
    if refs.MANAGER_RENAME:  # pragma: no cover - 防御性
        raise RuntimeError("本仓库不支持重命名/重签管理器（会触发内核证书白名单死锁）")
    steps = [
        "内核侧写入管理器证书白名单 = 上游默认（不注入自定义证书）",
        f"发布管理器 APK：{pin.manager_apk}",
    ]
    if pin.legacy_uapi:
        steps.append("给 ksud 源码打 uapi=0 兼容补丁，并把编译出的 ksud 作为产物一起发布")
    return PairingReport(
        pin=pin,
        manager_apk=pin.manager_apk,
        rename_manager=False,
        ksud_patch_needed=pin.legacy_uapi,
        steps=steps,
    )


def patch_ksud(src_root: Path) -> bool:
    """给 ksud 源码打 uapi 兼容补丁。返回是否发生过修改。

    * 已打过（含标记）-> 直接返回 False；
    * 找不到目标函数 -> 抛错（宁可构建失败，也不要产出"看起来成功但管理器用不了"的内核）。
    """
    target = src_root / KSUD_FILE
    if not target.is_file():
        raise FileNotFoundError(f"未找到 {target}（KSU 源码结构可能变化，需要更新 kbx/manager.py）")
    text = target.read_text(encoding="utf-8")
    if KSUD_UAPI_PATCH_MARKER in text:
        return False
    if _ORIGINAL not in text:
        raise RuntimeError(
            f"{target} 里没有找到 ensure_uapi_version_matched 的预期实现，"
            "无法安全打补丁（上游可能已改动，请更新 kbx/manager.py 后再构建）"
        )
    target.write_text(text.replace(_ORIGINAL, _PATCHED), encoding="utf-8")
    return True


def pin_driver_version(src_root: Path, version_code: int) -> bool:
    """把内核侧驱动版本号固定为配套值（0 表示不改）。"""
    if not version_code:
        return False
    candidates = [
        Path("kernel/KernelSU.h"),
        Path("kernel/include/ksu.h"),
        Path("kernel/ksu.h"),
    ]
    for rel in candidates:
        f = src_root / rel
        if f.is_file():
            text = f.read_text(encoding="utf-8")
            if "KERNEL_SU_VERSION" in text:
                import re

                new = re.sub(
                    r"#define\s+KERNEL_SU_VERSION\s+\d+",
                    f"#define KERNEL_SU_VERSION {version_code}",
                    text,
                )
                if new != text:
                    f.write_text(new, encoding="utf-8")
                    return True
    return False
