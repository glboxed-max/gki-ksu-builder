"""构建输入：定义、校验、命名。

原则：**先在本地把配置问题全部报出来**，而不是等 CI 跑到第 40 分钟才失败。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from . import refs
from .refs import KernelLine, KsuPin, RefError

OS_PATCH_RE = re.compile(r"^(latest|\d{4}-\d{2})$")
SUB_LEVEL_RE = re.compile(r"^(X|[0-9]{1,4})$", re.IGNORECASE)


@dataclass(frozen=True)
class BuildInputs:
    android: str = "android14"
    kernel: str = "6.1"
    sub_level: str = "138"
    os_patch_level: str = "latest"
    ksu: str = "sukisu-13000"
    features: tuple[str, ...] = ()
    zram_extra_algos: tuple[str, ...] = ()
    revision: str = "r1"
    custom_kernel_name: str | None = None

    # ---------------- 派生属性 ----------------
    @property
    def line(self) -> KernelLine:
        return refs.kernel_line(self.android, self.kernel)

    @property
    def pin(self) -> KsuPin:
        return refs.ksu_pin(self.ksu)

    @property
    def with_susfs(self) -> bool:
        return "susfs" in self.features

    def slug(self) -> str:
        """产物文件名用的标识，例如 android14-6.1.138-2026-07。"""
        patch = self.os_patch_level
        return f"{self.android}-{self.kernel}.{self.sub_level}-{patch}"

    def with_features(self, names: tuple[str, ...]) -> BuildInputs:
        return replace(self, features=names)

    # ---------------- 校验 ----------------
    def validate(self) -> list[str]:
        problems: list[str] = []
        if self.android not in {f"android{v}" for v in ("12", "13", "14", "15", "16")}:
            problems.append(f"android 取值不合法: {self.android}")
        try:
            refs.kernel_line(self.android, self.kernel)
        except RefError as exc:
            problems.append(str(exc))
        if not SUB_LEVEL_RE.match(self.sub_level):
            problems.append(f"sub_level 取值不合法: {self.sub_level}（应为数字或 X）")
        if not OS_PATCH_RE.match(self.os_patch_level):
            problems.append(f"os_patch_level 取值不合法: {self.os_patch_level}（应为 YYYY-MM 或 latest）")
        try:
            refs.ksu_pin(self.ksu)
        except RefError as exc:
            problems.append(str(exc))
        # 功能依赖与互斥交给 features 注册表检查（见 features.resolve）
        return problems

    def require_valid(self) -> BuildInputs:
        problems = self.validate()
        if problems:
            raise ValueError("配置有问题：\n  - " + "\n  - ".join(problems))
        return self


@dataclass
class PlanStep:
    """plan/build 里的一步。"""

    title: str
    detail: str = ""
    skipped: bool = False
    reason: str = ""
    actions: list[str] = field(default_factory=list)
