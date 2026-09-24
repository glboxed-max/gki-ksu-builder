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

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import refs
from .refs import KSUD_UAPI_PATCH_MARKER, KsuPin

KSUD_FILE = Path("userspace/ksud/src/ksucalls.rs")

KSUD_ORIGINAL = """pub fn ensure_uapi_version_matched() -> anyhow::Result<()> {
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

KSUD_PATCHED = f"""pub fn ensure_uapi_version_matched() -> anyhow::Result<()> {{
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
    """构建时打印并写进 manifest，明确管理器怎么配、设备上要注意什么。"""

    pin: KsuPin
    manager_apk: str
    rename_manager: bool
    steps: list[str] = field(default_factory=list)
    device_notes: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        out = [
            f"KSU 版本      : {self.pin.display}（驱动版本号 {self.pin.driver_version_code or '源码自带'}）",
            f"集成方式      : {self.pin.docs_flow}",
            f"配套管理器    : {self.manager_apk}（**上游原版，不改名、不重签**）",
            *[f"  · {s}" for s in self.steps],
        ]
        if self.device_notes:
            out.append("  设备侧注意事项:")
            out.extend(f"  · {n}" for n in self.device_notes)
        return out


def pairing(pin: KsuPin) -> PairingReport:
    if refs.MANAGER_RENAME:  # pragma: no cover - 防御性
        raise RuntimeError("本仓库不支持重命名/重签管理器（会触发内核证书白名单死锁）")
    return PairingReport(
        pin=pin,
        manager_apk=pin.manager_apk,
        rename_manager=False,
        steps=[
            "内核侧管理器证书白名单 = 上游默认（不注入自定义证书、不改写驱动版本号）",
            f"发布管理器 APK：{pin.manager_apk}（与驱动同代）",
        ],
        device_notes=[
            "安装**同一版本**的管理器；若之前装过其它管理器（尤其 LKM 安装模式留下的 ksud），"
            "先卸载干净再装，否则管理器可能报版本不匹配",
            "不要重命名 / 重签管理器：内核按证书信任且同一时刻只承认一个管理器 App",
        ],
    )


# --------------------------------------------------------------------------- #
# 以下是"曾经走过弯路"的实现，保留代码但**默认不启用**，仅作排障参考。
#
# 背景：实测中发现设备上残留了**更高版本**的 ksud（例如 3.3.0，它带 uapi 检查），
# 与钉住版本的驱动对不上，于是管理器报版本不匹配。正确的做法是按官方流程重装
# 匹配版本的管理器（管理器会带上配套的 ksud），而不是在构建期把新版补丁拉回来。
# 详见 README「我们严格按官方文档做」一节。
# --------------------------------------------------------------------------- #
def patch_ksud(src_root: Path) -> str:
    """给 ksud 源码打 uapi 兼容补丁。

    上游不同版本的 ksud 结构差别很大：
    * 有的版本把实现放在 userspace/ksud/src/ksucalls.rs；
    * 有的版本把实现拆到 ksucalls/ 下的多个文件里；
    * 钉住的 3.x 版本干脆没有 uapi 检查（此时**不需要**补丁）。

    因此这里递归查找目标函数，返回状态字符串（供 manifest 记录），
    只有"找到了却改不动"才是真异常。
    """
    roots = [src_root / KSUD_FILE]
    ksud_dir = src_root / "userspace" / "ksud"
    if ksud_dir.is_dir():
        roots.extend(sorted(ksud_dir.rglob("*.rs")))

    for target in roots:
        if not target.is_file():
            continue
        text = target.read_text(encoding="utf-8", errors="ignore")
        if KSUD_UAPI_PATCH_MARKER in text:
            return "already"
        if KSUD_ORIGINAL in text:
            target.write_text(text.replace(KSUD_ORIGINAL, KSUD_PATCHED), encoding="utf-8")
            return "patched"
    return "not-found"


def pin_driver_version(src_root: Path, version_code: int) -> str:
    """把内核侧驱动版本号固定为配套值（0 表示不改）。返回状态字符串。

    同样递归查找：不同版本的宏定义位置不同（KernelSU.h / ksu.h / include/ 下等）。
    """
    if not version_code:
        return "skipped"
    kernel_dir = src_root / "kernel"
    search = kernel_dir.rglob("*.h") if kernel_dir.is_dir() else iter(())
    for f in search:
        text = f.read_text(encoding="utf-8", errors="ignore")
        if "KERNEL_SU_VERSION" not in text:
            continue
        new = re.sub(r"(#define\s+KERNEL_SU_VERSION\s+)\d+", rf"\g<1>{version_code}", text)
        if new != text:
            f.write_text(new, encoding="utf-8")
            return f"pinned:{f.relative_to(src_root)}"
        return f"already:{f.relative_to(src_root)}"
    return "not-found"
