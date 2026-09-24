# gki-ksu-builder

> 重新设计的 GKI KernelSU / SUSFS 内核自动化构建仓库。
> 目标：**SukiSU 13000（钉住版）+ 全套附加功能** 能稳定构建，并且**管理器开箱可用**。

---

## 为什么重写

ABK 那套（以及野生的多数 fork）有四个结构性问题，本仓库从设计上避开：

| # | 旧方案的问题 | 本仓库的做法 |
|---|---|---|
| 1 | 用 6000+ 行 YAML 堆流程，逻辑难读、难测、缩进一错整个工作流失效 | **工作流只做三件事**：装工具链 → `python -m kbx build` → 传产物。全部逻辑在 Python 里，可单测 |
| 2 | 钉住旧版本（13000）时，驱动报 `uapi=0`，而管理器/ksud 期望非 0 → 判定"版本不匹配"→ 显示"未安装" | 构建时**自动给 ksud 打 uapi 兼容补丁**，并把它作为产物一起发布 |
| 3 | 为了换包名而**重签管理器**，导致内核证书白名单与管理器对不上（管理器身份死锁） | **绝不改名、绝不重签**管理器；内核信任上游证书，管理器用**同代上游 APK** |
| 4 | 构建完不知道"哪些功能真的打进去了" | 每个功能都是独立模块 + **能力闸门**，构建产出 `build-manifest.json` 明确记录实际生效的功能与来源提交 |

## 设计

```
kbx/
├── inputs.py      构建输入（带校验，配置错误在 30 秒内报出来，不等一小时）
├── refs.py        版本固定表：KSU 版本 / 同代 SUSFS / 各内核线源码分支
├── features/      一个功能一个模块，每个都能"声明自己能不能用于该内核线"
│   ├── susfs.py       SUSFS 内核侧 + KSU 侧补丁（按内核线选同代提交）
│   ├── kpm.py         KPM（SukiSU 3.x 内核模块支持）
│   ├── zram.py        ZRAM 增强算法 / 完整算法（6.12 自动跳过）
│   ├── security.py    BBG 防格机（Baseband Guard LSM）/ DDK 防格机 LSM
│   ├── ntsync.py      NTsync
│   ├── net.py         网络增强（IPSet + BBR）
│   └── rekernel.py    Re-Kernel 驱动
├── pipeline.py    编排：拉源码 → 装 KSU → 打功能 → 配置 → 编译 → 打包，全程记录 manifest
├── manager.py     管理器配对：选同代上游 APK + 打 uapi 补丁的 ksud（不改名不重签）
├── packaging.py   AnyKernel3 / boot.img（含 os_version 修正、旧管理器残留清理）
└── cli.py         `plan`（干跑，秒级看会做什么）/ `build`（真构建）/ `list-refs`
```

### 关键设计点

- **能力闸门**：每个功能自己声明适用范围，例如
  `zram_full_algos` 在 `android16-6.12` 上自动跳过；`susfs` 在某条线缺同代补丁时拒绝并给出原因。
  `plan` 会把这些决定打印出来，**不构建也能先确认**。
- **同代配对**：KSU 驱动、配套 `ksud`、管理器 APK 三者必须同来源提交，仓库在 `refs.py` 里维护这张表。
- **可测试**：`tests/` 单测覆盖固定表完整性与闸门逻辑，本地秒级跑完，不依赖 GitHub。

## 我们严格按"钉住版本自己的官方文档"来做

构建流程的每一步都能在**所选版本自带的文档**里找到出处，不引入文档之外的做法。
以 SukiSU v3.1.5（versionCode 13000，提交 `fa060dca…`）为例：

| 步骤 | 官方文档出处 |
|---|---|
| 集成 KernelSU | `docs/README.md`「如何添加」：在**内核源码根目录**执行 `kernel/setup.sh <分支或提交>`（脚本自行克隆并改写 `drivers/Kconfig`、`drivers/Makefile`） |
| SUSFS | `docs/README.md`：「使用 main 分支（**需要手动集成 susfs**）」→ 本仓库取**同代** susfs4ksu 提交，打内核侧 `50_add_susfs_in_*.patch` + KSU 侧 `10_enable_susfs_for_ksu.patch` |
| KPM | `docs/README.md`「KPM 支持」：源码就在 `kernel/kpm/`，只需 `CONFIG_KPM=y`；GKI 2.0 默认钩子是 KPROBES，需要 `CONFIG_KPROBES=y` |
| 管理器 | 与驱动**同代**的上游 APK，不改名、不重签（内核按证书信任管理器） |
| 刷写 | AnyKernel3（官方文档推荐的 GKI 刷写方式） |

### 明确**不做**的事（走过的弯路，留个记录）

1. ❌ **不给 ksud 打「uapi 兼容」补丁**：官方文档里没有这一步。实测证明设备侧
   "管理器报版本不匹配"的真因是**设备里残留了更高版本的 ksud**（旧 LKM 安装模式留下的），
   正确做法是把旧管理器/ksud 卸干净，再装**同版本**管理器。
2. ❌ **不改写驱动 `KERNEL_SU_VERSION`**：版本号用该版本源码自带的，不去"对号入座"。
3. ❌ **不重命名 / 不重签管理器**：内核只承认一个管理器 App，重签会让它认不到。

> 这些弯路对应的代码仍保留在 `kbx/manager.py`，但**默认不启用**、并标注为"排障参考"，
> 以免以后重复踩坑（也有单测覆盖其行为）。

## 用法

```bash
# 看某条配置会做什么（不构建）
python -m kbx plan --android android14 --kernel 6.1 --sub-level 138 \
    --ksu sukisu-13000 --with susfs,kpm,zram_enhanced,bbg,ntsync,net_enhanced,rekernel

# 真构建（需要在有内核源码与工具链的环境）
python -m kbx build --config build.toml

# 列出所有固定版本
python -m kbx list-refs
```

GitHub Actions：`Actions → Build → Run workflow`，填 Android/Kernel/Sub-level 与功能开关即可。

## 产物

| 产物 | 说明 |
|---|---|
| `*-AnyKernel3.zip` | 推荐刷写方式（保留设备 os_version/AVB，自动清理旧 LKM 残留） |
| `*-boot.img` / `-gz` / `-lz4` | 按内核压缩格式选择 |
| `manager-<版本>.apk` | **同代上游管理器**（未改名、未重签） |
| `ksud` | 打过 uapi 兼容补丁的 ksud，供旧内核使用 |
| `build-manifest.json` | 本次构建实际生效的功能、来源提交、跳过原因 |

## 状态与路线

- [x] 骨架与 `plan`/`build` 流程、固定表、能力闸门、单测
- [x] 三个已知坑的规避逻辑（uapi 补丁 / 同代配对 / 不改名重签）
- [ ] 各功能补丁在内核线上的逐条验证（需要 CI 跑通）
- [ ] OnePlus/Oplus 机型线（另一套 manifest）

> 功能补丁来源：susfs4ksu、SukiSU_patch、Baseband-guard、Re-Kernel、NTsync、Droidspaces 等，
> 每个功能的来源仓库与提交都记在 `refs.py`，并在 manifest 里显示。

## 许可

与上游保持一致（GPL-2.0 / GPL-3.0 等），详见 `THIRD_PARTY_NOTICES.md`。
