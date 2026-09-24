"""命令行入口：`python -m kbx <plan|build|list-refs|features>`。"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__, refs
from .features import ALL_FEATURES, REGISTRY
from .inputs import BuildInputs
from .pipeline import build, plan

LOG_FORMAT = "%(levelname)s %(message)s"


def _bool(value: str) -> str:
    return value.strip().lower()


def _split(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(x.strip() for x in value.split(",") if x.strip())


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--android", default="android14", help="如 android14")
    p.add_argument("--kernel", default="6.1", help="如 6.1 / 6.6 / 6.12")
    p.add_argument("--sub-level", default="138", help="子版本号，或 X 表示 LTS")
    p.add_argument("--os-patch-level", default="latest", help="YYYY-MM 或 latest")
    p.add_argument("--ksu", default="sukisu-13000", help="KSU 版本 key（见 list-refs）")
    p.add_argument("--with", dest="features", default="", help="逗号分隔的功能名（见 features）")
    p.add_argument("--zram-algos", default="", help="额外 ZRAM 算法，逗号分隔")
    p.add_argument("--revision", default="r1", help="android12 的 GKI revision")


def _force_utf8() -> None:
    """Windows 控制台默认 GBK，打不出 ✅/⏭️ 这类字符；统一切到 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # pragma: no cover - 少数环境不支持
                pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8()
    parser = argparse.ArgumentParser(prog="kbx", description="GKI KernelSU/SUSFS 构建")
    parser.add_argument("--version", action="version", version=f"kbx {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_plan = sub.add_parser("plan", help="打印构建计划（离线、秒级）")
    _add_common(p_plan)

    p_build = sub.add_parser("build", help="真正构建")
    _add_common(p_build)
    p_build.add_argument("--out", default="out", help="产物目录")
    p_build.add_argument("--dry-run", action="store_true", help="只打印会执行的命令")

    sub.add_parser("list-refs", help="列出固定版本表")
    sub.add_parser("features", help="列出可选功能")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format=LOG_FORMAT)

    if args.cmd == "list-refs":
        print("KSU 版本:")
        for key, pin in sorted(refs.KSU_PINS.items()):
            print(f"  {key:<16} {pin.display:<22} ref={pin.ref[:12]} driver={pin.driver_version_code or '-'}")
        print("\n内核线（同代 SUSFS 提交）:")
        for key, line in sorted(refs.KERNEL_LINES.items()):
            ref = refs.SUSFS_SAME_ERA.get(key) or "(无同代补丁，SUSFS 自动跳过)"
            print(f"  {key:<16} {ref}")
        return 0

    if args.cmd == "features":
        print("可选功能:")
        for name in ALL_FEATURES:
            f = REGISTRY[name]
            print(f"  {name:<16} [{f.status:<8}] {f.title}")
        return 0

    inputs = BuildInputs(
        android=args.android,
        kernel=args.kernel,
        sub_level=args.sub_level,
        os_patch_level=args.os_patch_level,
        ksu=args.ksu,
        features=_split(args.features),
        zram_extra_algos=_split(args.zram_algos),
        revision=args.revision,
    )
    problems = inputs.validate()
    if problems:
        print("配置有问题:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 2

    if args.cmd == "plan":
        print(plan(inputs).render())
        return 0

    if args.cmd == "build":
        build(inputs, Path(args.out), dry_run=args.dry_run)
        return 0

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
