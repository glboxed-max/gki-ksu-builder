# 第三方来源与许可

本仓库**不包含**任何成品二进制，只在构建时从下列上游拉取源码 / 补丁。
各上游的许可与版权归其作者所有，分发产物时请一并遵守。

| 组件 | 仓库 | 用途 | 许可 |
|---|---|---|---|
| KernelSU | https://github.com/tiann/KernelSU | 官方内置驱动 | GPL-3.0 |
| KernelSU-Next | https://github.com/KernelSU-Next/KernelSU-Next | 分支驱动 | GPL-3.0 |
| SukiSU-Ultra | https://github.com/SukiSU-Ultra/SukiSU-Ultra | 驱动 + ksud + 管理器 | GPL-3.0 |
| ReSukiSU | https://github.com/ReSukiSU/ReSukiSU | 分支驱动 | GPL-3.0 |
| susfs4ksu | https://gitlab.com/simonpunk/susfs4ksu | SUSFS 内核侧/KSU 侧补丁 | GPL-2.0 |
| kernel_patches | https://github.com/WildKernels/kernel_patches | 通用内核补丁（含 NTsync 等） | 见仓库 |
| SukiSU_patch | https://github.com/ShirkNeko/SukiSU_patch | ZRAM / LZ4KD 等附加补丁 | 见仓库 |
| Baseband-guard | https://github.com/vc-teahouse/Baseband-guard | BBG 防格机（LSM） | GPL-2.0 |
| Re-Kernel | https://github.com/Sakion-Team/Re-Kernel | Re-Kernel 驱动 | GPL-2.0 |
| AnyKernel3 | https://github.com/WildKernels/AnyKernel3 | 通用刷机包模板 | GPL-2.0 |
| AOSP kernel/common | https://android.googlesource.com/kernel/common | GKI 内核源码 | GPL-2.0 |

## 关于管理器（重要）

本仓库**不重命名、不重签**任何管理器 APK：

* 内核按签名证书信任管理器，且同一时刻只承认一个"管理器 App"；
* 重签会让内核内的证书摘要与管理器不一致，造成"驱动在跑但管理器显示未安装"的死锁；
* 因此这里只做**同代配对**：内核信任上游默认证书，产物里附带**上游原版**管理器 APK。

## 关于 ksud 补丁

对钉住的旧版 KernelSU（如 13000），驱动会报告 `uapi=0`。本仓库会在构建时给
**ksud 源码**打一个兼容补丁（`kbx/manager.py`），其行为与上游仓库中同类补丁一致：
仅在 kernel uapi 为 0 时跳过版本相等检查，不修改任何安全判断逻辑。
