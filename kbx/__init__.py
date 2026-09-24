"""kbx —— GKI KernelSU / SUSFS 内核自动化构建。

设计目标（详见 README）：
1. 逻辑在 Python 里，工作流只负责装工具链与调用；
2. 钉住旧版 KSU 时自动处理 uapi 兼容（13000 的坑）；
3. 管理器绝不改名、绝不重签，只做"同代配对"；
4. 每次构建产出 build-manifest.json，明确记录实际生效的功能。
"""

__version__ = "0.1.0"

MANIFEST_NAME = "build-manifest.json"
