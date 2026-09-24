#!/usr/bin/env python3
"""工作流自检：YAML 是否可解析 + 每个 run: 块的 shell 语法是否正确。

教训：把大段 shell 塞进 YAML 时，缩进一错整个 workflow 会失效，
甚至出现"YAML 看着没错、脚本其实语法坏了"的情况。这个脚本把两件事都验一遍。

用法：python scripts/check_workflows.py [-v]
退出码非 0 表示有问题（可直接在 CI 里当门禁）。
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))


def yaml_ok(path: Path) -> tuple[bool, str]:
    try:
        import yaml  # type: ignore
    except ImportError:
        return True, "（未安装 PyYAML，跳过 YAML 解析）"
    try:
        yaml.safe_load(path.read_text(encoding="utf-8"))
        return True, "YAML OK"
    except Exception as exc:  # noqa: BLE001
        return False, f"YAML 解析失败: {exc}"


def extract_run_blocks(text: str) -> list[tuple[int, str]]:
    """抽取 `run: |` 块（缩进感知，不依赖 YAML 库）。"""
    blocks: list[tuple[int, str]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^(\s*)run:\s*\|\s*$", line)
        if not m:
            i += 1
            continue
        indent = len(m.group(1))
        body: list[str] = []
        i += 1
        while i < len(lines):
            cur = lines[i]
            if cur.strip() == "":
                body.append("")
                i += 1
                continue
            cur_indent = len(cur) - len(cur.lstrip(" "))
            if cur_indent <= indent:
                break
            body.append(cur)
            i += 1
        blocks.append((indent, "\n".join(body)))
    return blocks


def dedent(block: str) -> str:
    lines = [ln for ln in block.splitlines() if ln.strip()]
    if not lines:
        return ""
    common = min(len(ln) - len(ln.lstrip(" ")) for ln in lines)
    return "\n".join(ln[common:] if ln.strip() else "" for ln in block.splitlines())


def bash_syntax(script: str) -> tuple[bool, str]:
    """用 `bash -n -c <脚本>` 检查语法。

    不落地临时文件：Windows 的 Git-Bash 认不了 `C:\\...` 路径，而 `-c` 方式
    在 Linux 与 Git-Bash 下行为一致（CI 与本地同一套检查）。
    """
    try:
        proc = subprocess.run(["bash", "-n", "-c", script], capture_output=True, text=True)
    except FileNotFoundError:
        return True, "（未找到 bash，跳过 shell 语法检查）"
    if proc.returncode == 0:
        return True, "shell 语法 OK"
    return False, (proc.stderr or "").strip()[:400]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    problems = 0
    for wf in WORKFLOWS:
        text = wf.read_text(encoding="utf-8")
        ok, msg = yaml_ok(wf)
        print(f"[{'OK ' if ok else 'FAIL'}] {wf.relative_to(ROOT)} — {msg}")
        if not ok:
            problems += 1
        for idx, (indent, block) in enumerate(extract_run_blocks(text), 1):
            # GitHub 表达式先整体替换成单个占位符：既保留语法结构，
            # 又不会因为变成 `${ ... }` 而产生假的语法错误。
            script = re.sub(r"\$\{\{[^}]*\}\}", "EXPR", dedent(block))
            ok, msg = bash_syntax(f"#!/usr/bin/env bash\nset -e\n{script}\n")
            if not ok:
                print(f"       run#{idx} (indent={indent}) 语法错误: {msg}")
                problems += 1
            elif args.verbose:
                print(f"       run#{idx} (indent={indent}) OK")
    print(f"\n结论: {'全部通过' if problems == 0 else f'{problems} 个问题'}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
