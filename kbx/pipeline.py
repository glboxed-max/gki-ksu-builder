"""构建编排：plan（秒级、离线）与 build（真构建）。

plan 与 build 共用同一份步骤定义，所以 **plan 里看到的就是 build 会做的**，
不会出现"文档写一套、脚本做另一套"。
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__, refs
from .features import FeatureContext, ResolvedFeatures, resolve
from .inputs import BuildInputs, PlanStep
from .manager import PairingReport, pairing, patch_ksud, pin_driver_version
from .packaging import build_anykernel, build_boot_image, write_manifest

AOSP_KERNEL = "https://android.googlesource.com/kernel/common"
log = logging.getLogger("kbx")


@dataclass
class Plan:
    inputs: BuildInputs
    features: ResolvedFeatures
    pairing: PairingReport
    steps: list[PlanStep] = field(default_factory=list)

    def render(self) -> str:
        out: list[str] = []
        i = self.inputs
        out.append(f"== 构建计划: {i.slug()} ==")
        out.append(f"内核源码 : kernel/common @ {i.line.aosp_branch}（sub-level {i.sub_level}）")
        out.append(f"KSU      : {i.pin.display}  ref={i.pin.ref[:12]}")
        out.append("")
        for n, line in enumerate(self.pairing.lines(), 1):
            out.append(("管理器配对: " if n == 1 else "            ") + line)
        out.append("")
        out.append(f"功能（生效 {len(self.features.active)} 项）:")
        for name in self.features.active:
            f = refs.FEATURE_SOURCES.get(name)
            title = _feature_title(name)
            out.append(f"  ✅ {name:<16} {title}" + (f"  ← {f.repo}" if f else ""))
        if self.features.skipped:
            out.append("功能（自动跳过）:")
            for name, why in self.features.skipped.items():
                out.append(f"  ⏭️  {name:<16} {why}")
        out.append("")
        out.append("步骤:")
        for n, step in enumerate(self.steps, 1):
            mark = "⏭️ " if step.skipped else "  "
            out.append(f"  {mark}{n:>2}. {step.title}")
            if step.detail:
                out.append(f"        {step.detail}")
            for action in step.actions:
                out.append(f"        · {action}")
            if step.skipped and step.reason:
                out.append(f"        (跳过: {step.reason})")
        return "\n".join(out)


def _feature_title(name: str) -> str:
    from .features import REGISTRY

    return REGISTRY[name].title if name in REGISTRY else name


def _context(inputs: BuildInputs, src_root: Path, work: Path, *, offline: bool) -> FeatureContext:
    """offline=True（plan）时所有 IO 都是空操作。"""

    def _noop_clone(repo: str, ref: str | None, name: str) -> Path:
        return work / name

    def _noop(*_a, **_k) -> None:
        return None

    return FeatureContext(
        inputs=inputs,
        line=inputs.line,
        pin=inputs.pin,
        src_root=src_root,
        work=work,
        clone=_noop_clone if offline else _real_clone(work),
        apply_patch=_noop if offline else _real_apply_patch(),
        inject_config=_noop if offline else _real_inject_config(inputs),
        run=_noop if offline else _real_run(),
    )


def plan(inputs: BuildInputs) -> Plan:
    inputs.require_valid()
    work = Path("build") / inputs.slug()
    ctx = _context(inputs, work / "kernel", work, offline=True)
    features = resolve(inputs.features, ctx)
    pair = pairing(inputs.pin)

    steps: list[PlanStep] = []
    steps.append(
        PlanStep(
            "拉取内核源码",
            detail=f"{AOSP_KERNEL} @ {inputs.line.aosp_branch}",
            actions=[f"检出 sub-level {inputs.sub_level} 对应提交（找不到则用分支 HEAD）"],
        )
    )
    steps.append(
        PlanStep(
            "集成 KernelSU",
            detail=f"{inputs.pin.repo} @ {inputs.pin.ref[:12]}",
            actions=[
                "拷贝 kernel/ 到内核树并写入 Kconfig/Makefile（或执行上游 setup.sh）",
                f"固定驱动版本号 {inputs.pin.driver_version_code or '（源码自带）'}",
                *(
                    ["给 ksud 打 uapi=0 兼容补丁"]
                    if pair.ksud_patch_needed
                    else []
                ),
            ],
        )
    )
    for name in inputs.features:
        from .features import REGISTRY, feature

        f = feature(name)
        if name in features.skipped:
            steps.append(PlanStep(f"功能：{f.title}", skipped=True, reason=features.skipped[name]))
            continue
        steps.append(PlanStep(f"功能：{f.title}", actions=f.describe(ctx)))

    steps.append(
        PlanStep(
            "注入配置并编译",
            actions=[
                "把上面的 CONFIG_* 写进 fragment / gki_defconfig",
                "6.12+ 用 Kleaf（bazel），其余用 build/build.sh",
            ],
        )
    )
    steps.append(
        PlanStep(
            "打包",
            detail=f"产物前缀 {inputs.slug()}",
            actions=[
                "AnyKernel3（含旧管理器残留清理）",
                "boot.img（写 os_version / os_patch_level，避免防回滚卡 fastboot）",
                f"管理器：{pair.manager_apk}（原版）",
                "ksud（若为旧版驱动）",
                "build-manifest.json",
            ],
        )
    )
    return Plan(inputs=inputs, features=features, pairing=pair, steps=steps)


def build(inputs: BuildInputs, out_dir: Path, *, dry_run: bool = False) -> dict:
    """真构建。dry_run=True 时只打印命令。"""
    p = plan(inputs)
    log.info("\n%s", p.render())
    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / "work"
    work.mkdir(exist_ok=True)
    src = work / "kernel"
    manifest: dict = {
        "kbx_version": __version__,
        "inputs": {
            "android": inputs.android,
            "kernel": inputs.kernel,
            "sub_level": inputs.sub_level,
            "os_patch_level": inputs.os_patch_level,
            "ksu": inputs.ksu,
        },
        "ksu": {"repo": inputs.pin.repo, "ref": inputs.pin.ref, "display": inputs.pin.display},
        "susfs_ref": refs.susfs_ref_for(inputs.line, inputs.pin),
        "features_active": p.features.active,
        "features_skipped": p.features.skipped,
        "manager": {
            "apk": p.pairing.manager_apk,
            "renamed": False,
            "ksud_patched": p.pairing.ksud_patch_needed,
        },
        "artifacts": [],
    }

    def sh(cmd: str, cwd: Path | None = None) -> None:
        log.info("$ %s", cmd)
        if dry_run:
            return
        subprocess.run(cmd, shell=True, check=True, cwd=cwd)

    # 1) 内核源码
    if not src.exists():
        sh(f"git clone --depth 1 -b {inputs.line.aosp_branch} {AOSP_KERNEL} {src}")
    if inputs.sub_level.upper() != "X":
        tag = f"{inputs.line.aosp_branch}.{inputs.sub_level}"
        sh(f"git -C {src} fetch --depth 1 origin 'refs/tags/{tag}*' || true")
        sh(f"git -C {src} checkout -q '$(git -C {src} tag -l \"{tag}*\" | head -n1)' || true")

    # 2) KernelSU
    ksu = work / "KernelSU"
    if not ksu.exists():
        sh(f"git clone {inputs.pin.repo} {ksu}")
        sh(f"git -C {ksu} checkout -q {inputs.pin.ref}")
    if (ksu / "kernel" / "setup.sh").is_file():
        sh(f"sh {ksu / 'kernel' / 'setup.sh'}", cwd=src)
    else:
        sh(f"cp -a {ksu / 'kernel'} {src / 'kernel'}")
        sh(f"cat {ksu / 'kernel' / 'Kconfig'} >> {src / 'drivers' / 'Kconfig'} || true")
    if not dry_run:
        pin_driver_version(src, inputs.pin.driver_version_code)
        if inputs.pin.legacy_uapi:
            patch_ksud(src)
            manifest["ksud_patched"] = True

    # 3) 功能
    ctx = _context(inputs, src, work, offline=dry_run)
    for name in p.features.active:
        from .features import feature

        log.info("== 功能: %s ==", name)
        feature(name).apply(ctx)
    manifest["feature_notes"] = ctx.notes

    # 4) 编译（GKI）
    if inputs.line.is_612:
        sh("tools/bazel run //common:kernel_aarch64_dist -- --dist_dir=out/dist", cwd=src)
        image = src / "out" / "dist" / "Image.lz4"
    else:
        sh(
            "BUILD_CONFIG=common/build.config.gki.aarch64 "
            "ARCH=arm64 ABI=aarch64 "
            "build/build.sh",
            cwd=src,
        )
        image = src / "out" / "android14-6.1" / "dist" / "Image.lz4"

    # 5) 打包
    if not dry_run and image.is_file():
        zip_path = build_anykernel(src / "AnyKernel3", image, inputs, out_dir / f"{inputs.slug()}-AnyKernel3.zip")
        manifest["artifacts"].append(str(zip_path))
    manifest["steps"] = [s.title for s in p.steps]

    if not dry_run:
        write_manifest(out_dir, manifest)
    log.info("完成: %s", json.dumps(manifest["artifacts"], ensure_ascii=False) or "(dry-run)")
    return manifest


# --------------------------------------------------------------------------- #
# 真实 IO 实现（build 用）
# --------------------------------------------------------------------------- #
def _real_clone(work: Path):
    def clone(repo: str, ref: str | None, name: str) -> Path:
        dest = work / name
        if not dest.exists():
            subprocess.run(f"git clone {repo} {dest}", shell=True, check=True)
            if ref:
                subprocess.run(f"git -C {dest} checkout -q {ref}", shell=True, check=True)
        return dest

    return clone


def _real_apply_patch():
    def apply_patch(patch: Path, target: Path) -> None:
        subprocess.run(f"git -C {target} apply --3way {patch}", shell=True, check=True)

    return apply_patch


def _real_inject_config(inputs: BuildInputs):
    def inject(key: str, enable: bool = True) -> None:
        line = f"{key}=y" if enable else f"# {key} is not set"
        entry = (line, inputs.slug())
        _FRAGMENTS.setdefault(entry, None)

    return inject


def _real_run():
    def run(cmd: str, cwd: Path) -> None:
        subprocess.run(cmd, shell=True, check=True, cwd=cwd)

    return run


#: build 过程中收集的配置片段，编译前统一写出
_FRAGMENTS: dict[tuple[str, str], None] = {}


def fragments() -> list[str]:
    return [k[0] for k in _FRAGMENTS]


def stage_fragments(src_root: Path) -> Path:
    frag = src_root / "kbx.fragment"
    frag.write_text("\n".join(fragments()) + "\n", encoding="utf-8")
    return frag


def reset_fragments() -> None:
    _FRAGMENTS.clear()


def clean(work: Path) -> None:
    if work.exists():
        shutil.rmtree(work)
