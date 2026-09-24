#!/usr/bin/env python3
"""生成 GitHub Actions 的 matrix JSON（供 `>> $GITHUB_OUTPUT` 使用）。

放在脚本里而不是内联在 YAML，是为了：可本地运行、可单测、不受 YAML 缩进影响。
"""

from __future__ import annotations

import argparse
import json


def build(include_612: bool, sub_level: str = "X") -> dict:
    lines = ["android12-5.10", "android13-5.15", "android14-6.1", "android15-6.6"]
    if include_612:
        lines.append("android16-6.12")
    include = []
    for line in lines:
        android, kernel = line.split("-", 1)
        include.append({"android": android, "kernel": kernel, "sub_level": sub_level, "line": line})
    return {"include": include}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-612", default="false", help="true/false")
    ap.add_argument("--sub-level", default="X")
    ap.add_argument("--format", choices=("gh-output", "json"), default="gh-output")
    args = ap.parse_args()

    data = build(args.with_612.strip().lower() == "true", args.sub_level)
    if args.format == "json":
        print(json.dumps(data))
    else:
        print("matrix=" + json.dumps(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
