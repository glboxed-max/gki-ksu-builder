"""功能注册表与能力闸门。

每个功能：
* 自己声明**能不能用在某条内核线**（`applies`），不能就给出原因（plan 会显示）；
* 自己声明**需要哪些前置功能**（`requires`）；
* 提供 `describe()` 让 `plan` 在不构建的情况下说清"会改哪些东西"；
* 提供 `apply()` 真正动手（只在 `build` 时调用）。

这就是本仓库相对旧方案的核心变化：**功能做成模块 + 闸门 + 可测试**，
而不是散在一个几千行的 workflow 里的 if/else。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from ..inputs import BuildInputs
from ..refs import KernelLine, KsuPin

log = logging.getLogger("kbx.features")


@dataclass
class FeatureContext:
    """功能执行时能拿到的一切。"""

    inputs: BuildInputs
    line: KernelLine
    pin: KsuPin
    src_root: Path  # 内核源码根目录
    work: Path  # 临时目录
    clone: Callable[[str, str | None, str], Path]  # (repo, ref, name) -> 目录
    apply_patch: Callable[[Path, Path], None]  # (patch 文件, 目标目录)
    inject_config: Callable[[str, bool], None]  # (CONFIG_XXX, 启用)
    run: Callable[[str, Path], None]  # (命令, 工作目录)
    notes: list[str] = field(default_factory=list)


class Feature:
    """功能基类。"""

    name: str = ""
    title: str = ""
    requires: tuple[str, ...] = ()
    status: str = "pending"  # verified / pending

    #: 能力闸门：返回 (是否可用, 不可用原因)
    def applies(self, ctx: FeatureContext) -> tuple[bool, str]:
        return True, ""

    #: plan 显示的动作清单
    def describe(self, ctx: FeatureContext) -> list[str]:
        return []

    #: 真正执行
    def apply(self, ctx: FeatureContext) -> None:  # pragma: no cover - 需真实源码
        raise NotImplementedError

    # ---------------- 供子类复用的工具 ----------------
    @staticmethod
    def need_susfs_ref(ctx: FeatureContext) -> str:
        ref = ctx.pin.susfs_ref or __import__("kbx.refs", fromlist=["SUSFS_SAME_ERA"]).SUSFS_SAME_ERA.get(
            ctx.line.key
        )
        if not ref:
            raise RuntimeError(f"{ctx.line.key} 没有同代 SUSFS 提交")
        return ref


# 注册表在文件末尾统一装配，避免循环导入
def _registry() -> dict[str, Feature]:
    from .kpm import KpmFeature
    from .net import NetEnhancedFeature
    from .ntsync import NTsyncFeature
    from .rekernel import ReKernelFeature
    from .security import BbgFeature, DdkLsmFeature
    from .susfs import SusfsFeature
    from .zram import ZramEnhancedFeature, ZramFullAlgosFeature

    items: Iterable[Feature] = (
        SusfsFeature(),
        KpmFeature(),
        ZramEnhancedFeature(),
        ZramFullAlgosFeature(),
        BbgFeature(),
        DdkLsmFeature(),
        NTsyncFeature(),
        NetEnhancedFeature(),
        ReKernelFeature(),
    )
    return {f.name: f for f in items}


REGISTRY: dict[str, Feature] = _registry()

#: 全部可选功能（按依赖顺序给出建议顺序）
ALL_FEATURES: tuple[str, ...] = tuple(REGISTRY)


def feature(name: str) -> Feature:
    try:
        return REGISTRY[name]
    except KeyError:
        known = ", ".join(ALL_FEATURES)
        raise KeyError(f"未知功能 {name}（可用：{known}）") from None


@dataclass
class ResolvedFeatures:
    active: list[str]
    skipped: dict[str, str]  # name -> 原因

    @property
    def reasons(self) -> list[str]:
        return [f"{n}: {r}" for n, r in self.skipped.items()]


def resolve(names: Iterable[str], ctx: FeatureContext) -> ResolvedFeatures:
    """把用户选择的功能解析成"生效 / 跳过（附原因）"。

    处理三件事：
    1. 未知功能 -> 直接报错；
    2. 依赖缺失 -> 跳过并说明；
    3. 能力闸门不通过 -> 跳过并说明。
    """
    active: list[str] = []
    skipped: dict[str, str] = {}
    wanted = list(dict.fromkeys(names))  # 去重且保序

    for n in wanted:
        feature(n)  # 触发未知功能检查

    for n in wanted:
        f = REGISTRY[n]
        missing = [d for d in f.requires if d not in wanted]
        if missing:
            skipped[n] = f"缺少前置功能 {'/'.join(missing)}"
            continue
        ok, why = f.applies(ctx)
        if not ok:
            skipped[n] = why
            continue
        active.append(n)

    # 依赖被跳过的，连带跳过
    changed = True
    while changed:
        changed = False
        for n in list(active):
            f = REGISTRY[n]
            broken = [d for d in f.requires if d in skipped]
            if broken:
                active.remove(n)
                skipped[n] = f"前置功能 {'/'.join(broken)} 被跳过"
                changed = True

    return ResolvedFeatures(active=active, skipped=skipped)
