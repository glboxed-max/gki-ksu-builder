"""打包：AnyKernel3 与 boot 镜像。

两条关键经验（来自实战排查）：
1. **boot 镜像必须写 os_version / os_patch_level**：否则 head 里是 0，
   高通 bootloader 会当作"降级刷机"拒绝引导（刷完停在 fastboot）。
2. **AnyKernel3 刷入时清理旧管理器残留**：旧 LKM 版 KernelSU 会抢先加载，
   导致管理器认不到内置驱动；清理只针对旧管理器组件，**绝不删模块**。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import zipfile
from pathlib import Path

from .inputs import BuildInputs

CLEANUP_FILES = (
    "ksuinit kernelsu.ko ksu.ko ksu_config init.ksu.rc ksuinit.rc init.ksu "
    "overlay.d/sbin/ksuinit overlay.d/sbin/kernelsu.ko"
).split()

# 注意：这里不能对 shell 代码用 str.format()（大括号会冲突），统一用占位符替换。
CLEANUP_SCRIPT_TEMPLATE = """#!/sbin/sh
# kbx: 刷入前清理旧 LKM 版 KernelSU 残留（只删旧管理器组件，模块一律保留）
KBX_FILES="__FILES__"

kbx_rd_has_lkm() {
  local d="$1" f
  [ -n "$d" ] && [ -d "$d" ] || return 1
  for f in $KBX_FILES init.real init.orig init.kernelsu; do
    [ -e "$d/$f" ] && return 0
  done
  return 1
}

kbx_rd_clean() {
  local d="$1" f b rc
  [ -n "$d" ] && [ -d "$d" ] || return 1
  for f in $KBX_FILES; do
    if [ -e "$d/$f" ]; then
      rm -rf "$d/$f"
      ui_print "  -> 删除旧管理器组件: $f"
    fi
  done
  for b in init.real init.orig init.kernelsu; do
    if [ -e "$d/$b" ]; then
      mv -f "$d/$b" "$d/init"
      ui_print "  -> 恢复 ramdisk 的 init（原被 $b 替换）"
      break
    fi
  done
  for rc in init.rc init.ksu.rc; do
    [ -f "$d/$rc" ] || continue
    if grep -q -e 'kernelsu\\.ko' -e 'ksuinit' "$d/$rc" 2>/dev/null; then
      sed -i -e '/kernelsu\\.ko/d' -e '/ksuinit/d' "$d/$rc"
      ui_print "  -> 清理 $rc 里旧的 LKM 加载项"
    fi
  done
  return 0
}

kbx_cleanup_ramdisk() {
  if kbx_rd_has_lkm "${RAMDISK:-}"; then
    ui_print "  -> ramdisk 里检测到旧管理器残留，开始清理"
    kbx_rd_clean "$RAMDISK"
  fi
  return 0
}
"""

CLEANUP_SCRIPT = CLEANUP_SCRIPT_TEMPLATE.replace("__FILES__", " ".join(CLEANUP_FILES))


def write_cleanup_script(anykernel_dir: Path) -> Path:
    target = anykernel_dir / "kbx-cleanup.sh"
    target.write_text(CLEANUP_SCRIPT, encoding="utf-8")
    return target


def patch_anykernel_sh(anykernel_dir: Path) -> bool:
    """在 anykernel.sh 里接入清理逻辑（幂等）。"""
    sh = anykernel_dir / "anykernel.sh"
    text = sh.read_text(encoding="utf-8")
    if "kbx-cleanup.sh" in text:
        return False
    lines = text.splitlines()
    out: list[str] = []
    for ln in lines:
        out.append(ln)
        if "ak3-core.sh" in ln and ln.strip().startswith("."):
            out.append(". kbx-cleanup.sh")
            out.append("kbx_cleanup_ramdisk || true")
    sh.write_text("\n".join(out) + "\n", encoding="utf-8")
    return True


def build_anykernel(anykernel_template: Path, image: Path, inputs: BuildInputs, out_zip: Path) -> Path:
    work = out_zip.parent / f"anykernel-{inputs.slug()}"
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(anykernel_template, work)
    shutil.copy2(image, work / "Image")
    write_cleanup_script(work)
    patch_anykernel_sh(work)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(work.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(work).as_posix())
    return out_zip


def build_boot_image(
    mkbootimg: Path,
    avbtool: Path | None,
    kernel: Path,
    ramdisk: Path | None,
    out_img: Path,
    inputs: BuildInputs,
    sign_key: Path | None = None,
) -> Path:
    """生成 boot.img —— **务必带 os_version / os_patch_level**。"""
    os_version = {
        "android12": "12.0.0",
        "android13": "13.0.0",
        "android14": "14.0.0",
        "android15": "15.0.0",
        "android16": "16.0.0",
    }[inputs.android]
    patch = inputs.os_patch_level if inputs.os_patch_level != "latest" else "2026-01"
    cmd = [
        "python3",
        str(mkbootimg),
        "--header_version",
        "4",
        "--kernel",
        str(kernel),
        "--output",
        str(out_img),
        "--os_version",
        os_version,
        "--os_patch_level",
        patch,
    ]
    if ramdisk and ramdisk.is_file():
        cmd += ["--ramdisk", str(ramdisk)]
    subprocess.run(cmd, check=True)
    if avbtool and sign_key:
        subprocess.run(
            [
                "python3",
                str(avbtool),
                "add_hash_footer",
                "--partition_name",
                "boot",
                "--partition_size",
                str(64 * 1024 * 1024),
                "--image",
                str(out_img),
                "--algorithm",
                "SHA256_RSA2048",
                "--key",
                str(sign_key),
            ],
            check=True,
        )
    return out_img


def write_manifest(out_dir: Path, data: dict) -> Path:
    path = out_dir / "build-manifest.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
