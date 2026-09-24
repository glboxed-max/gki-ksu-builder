"""构建编排：plan（秒级、离线）与 build（真构建）。

plan 与 build 共用同一份步骤定义，所以 **plan 里看到的就是 build 会做的**，
不会出现"文档写一套、脚本做另一套"。
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__, refs
from .features import FeatureContext, ResolvedFeatures, resolve
from .inputs import BuildInputs, PlanStep
from .manager import PairingReport, pairing
from .packaging import build_anykernel, build_boot_image, write_manifest

#: 内核源码：主源 + 镜像回退（googlesource 偶尔 502，必须有备选）
KERNEL_MIRRORS = (
    "https://android.googlesource.com/kernel/common",
    "https://github.com/aosp-mirror/kernel_common.git",
)
log = logging.getLogger("kbx")


def retry(fn, attempts: int = 3, base_delay: float = 5.0, what: str = "操作"):
    """带退避的重试。用于一切网络操作（克隆/拉取）——CI 里服务器抽风很常见。

    纯逻辑，可单测：最后一次仍失败时抛出最后一次的异常。
    """
    last: Exception | None = None
    for i in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - 网络层什么都可能抛
            last = exc
            log.warning("%s 第 %d/%d 次失败: %s", what, i, attempts, exc)
            if i < attempts:
                time.sleep(base_delay * i)  # 5s, 10s ...
    assert last is not None
    raise last


def pick_tag(prefix: str, ls_remote: str) -> str | None:
    """从 `git ls-remote --tags` 输出里挑出子版本对应的 tag。

    纯函数（可单测）：只保留 refs/tags/<prefix>...、排除 peeled 的 `^{}`，
    后缀里数字最大的优先（例如 ..._r02 > ..._r01）。
    """
    names: list[str] = []
    for raw in ls_remote.splitlines():
        parts = raw.split("\t")
        if len(parts) != 2:
            continue
        ref = parts[1].strip()
        if not ref.startswith("refs/tags/"):
            continue
        name = ref[len("refs/tags/") :]
        if name.endswith("^{}") or not name.startswith(prefix):
            continue
        names.append(name)
    if not names:
        return None

    def sort_key(name: str) -> list[int]:
        tail = name[len(prefix) :]
        numbers = [int(x) for x in re.findall(r"\d+", tail)]
        return numbers or [0]

    return sorted(names, key=sort_key)[-1]


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
            detail=f"{KERNEL_MIRRORS[0]} @ {inputs.line.aosp_branch}",
            actions=[
                f"检出 sub-level {inputs.sub_level} 对应提交（找不到则用分支 HEAD）",
                f"失败时按顺序回退镜像：{' → '.join(KERNEL_MIRRORS[1:]) or '（无）'}，并带重试",
            ],
        )
    )
    steps.append(
        PlanStep(
            "集成 KernelSU（严格按官方文档）",
            detail=f"{inputs.pin.repo_url} @ {inputs.pin.ref[:12]}",
            actions=[
                f"官方集成方式：{inputs.pin.docs_flow}",
                "脚本自行克隆 KernelSU、改写 drivers/Kconfig 与 drivers/Makefile",
                "不做文档之外的改动：不改驱动版本号、不给 ksud 打补丁",
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
            "device_notes": p.pairing.device_notes,
        },
        "artifacts": [],
    }

    def sh(cmd: str, cwd: Path | None = None) -> None:
        log.info("$ %s", cmd)
        if dry_run:
            return
        subprocess.run(cmd, shell=True, check=True, cwd=cwd)

    def capture(cmd: str) -> str:
        log.info("$ %s   # 读取输出", cmd)
        if dry_run:
            return ""
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return proc.stdout or ""

    # 1) 内核源码（sub-level -> tag 的解析放 Python 里做，不再用 shell 通配）
    if not src.exists() and not dry_run:
        used = None
        for mirror in KERNEL_MIRRORS:
            try:
                retry(
                    lambda m=mirror: subprocess.run(
                        f"git clone --depth 1 -b {inputs.line.aosp_branch} {m} {src}",
                        shell=True,
                        check=True,
                        cwd=None,
                    ),
                    attempts=2,
                    what=f"克隆内核源码({mirror})",
                )
                used = mirror
                break
            except Exception as exc:  # noqa: BLE001
                log.warning("镜像不可用 %s: %s", mirror, exc)
                shutil.rmtree(src, ignore_errors=True)
        if not used:
            raise RuntimeError("所有内核源码镜像都失败了，稍后重试（CI 上多为 googlesource 临时 502）")
        manifest["kernel_source"] = used
    elif dry_run:
        sh(f"git clone --depth 1 -b {inputs.line.aosp_branch} {KERNEL_MIRRORS[0]} {src}")

    if inputs.sub_level.upper() != "X":
        prefix = f"{inputs.line.aosp_branch}.{inputs.sub_level}"
        # 网络抖动不该让整个构建失败：tag 拉不到就退回分支 HEAD
        try:
            tag = pick_tag(prefix, capture(f"git -C {src} ls-remote --tags origin '{prefix}*'"))
            if tag:
                retry(lambda: subprocess.run(
                    f"git -C {src} fetch --depth 1 origin refs/tags/{tag}",
                    shell=True, check=True), what=f"拉取 tag {tag}")
                sh(f"git -C {src} checkout -q FETCH_HEAD")
            else:
                log.warning("没找到子版本 %s 的 tag（%s*），沿用分支 HEAD", inputs.sub_level, prefix)
        except Exception as exc:  # noqa: BLE001
            log.warning("子版本 tag 处理失败（%s），沿用 %s 分支 HEAD", exc, inputs.line.aosp_branch)

    # 2) KernelSU —— 严格按钉住版本的官方文档执行：
    #    「在内核源码的根目录下执行 kernel/setup.sh <分支或提交>」
    #    脚本自己负责把 KernelSU 克隆进内核树、并改写 drivers/Kconfig 与 Makefile。
    #    我们不做文档之外的额外改动（不改驱动版本号、不给 ksud 打补丁）。
    ksu = src / "KernelSU"
    if not ksu.exists() and not dry_run:
        retry(
            lambda: subprocess.run(f"git clone {inputs.pin.repo_url} {ksu}", shell=True, check=True),
            what="克隆 KernelSU",
        )
        retry(
            lambda: subprocess.run(
                f"git -C {ksu} checkout -q {inputs.pin.ref}", shell=True, check=True
            ),
            what="检出 KernelSU 提交",
        )
    elif dry_run:
        sh(f"git clone {inputs.pin.repo_url} {ksu}")
        sh(f"git -C {ksu} checkout -q {inputs.pin.ref}")
    setup = (ksu / "kernel" / "setup.sh").resolve()
    if dry_run:
        sh(f"sh {setup} {inputs.pin.ref}", cwd=src)  # 干跑只打印命令，不校验源码树
    elif setup.is_file():
        sh(f"sh {setup} {inputs.pin.ref}", cwd=src)  # 内核根目录 + 官方参数（提交）
    else:
        raise RuntimeError(
            f"{inputs.pin.ref} 里没有 kernel/setup.sh，无法按官方文档集成；"
            "请核对固定表 kbx/refs.py 里的 ref"
        )
    manifest["integration"] = "kernel/setup.sh（官方文档「如何添加」一节）"

    # 3) 功能
    from .features import feature

    reset_fragments()
    ctx = _context(inputs, src, work, offline=dry_run)
    for name in p.features.active:
        log.info("== 功能: %s ==", name)
        feature(name).apply(ctx)
    manifest["feature_notes"] = ctx.notes

    # 3.5) 把收集到的 CONFIG_* 真正写进内核配置（否则功能只改了源码、配置没生效）
    config_lines = fragments()
    manifest["config_lines"] = len(config_lines)
    if config_lines and not dry_run:
        gki = src / "arch" / "arm64" / "configs" / "gki_defconfig"
        gki.parent.mkdir(parents=True, exist_ok=True)
        with gki.open("a", encoding="utf-8") as fh:
            fh.write("\n# kbx: 功能开关\n" + "\n".join(config_lines) + "\n")
        manifest["config_fragment"] = str(gki.relative_to(src))
        log.info("已写入 %d 条配置到 %s", len(config_lines), manifest["config_fragment"])

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
    """功能模块用的克隆器：同样带重试（CI 上网络抖动不该毁掉整个构建）。"""

    def clone(repo: str, ref: str | None, name: str) -> Path:
        dest = work / name
        if not dest.exists():
            retry(
                lambda: subprocess.run(f"git clone {repo} {dest}", shell=True, check=True),
                what=f"克隆 {name}",
            )
            if ref:
                retry(
                    lambda: subprocess.run(
                        f"git -C {dest} checkout -q {ref}", shell=True, check=True
                    ),
                    what=f"检出 {name}",
                )
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
