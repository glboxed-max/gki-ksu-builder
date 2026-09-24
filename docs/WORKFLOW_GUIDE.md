# GitHub Actions 工作流入门（配内核构建实战）

> 这份文档是写给"要自己改构建流程"的人的。看完你能：
> ① 看懂 `.github/workflows/*.yml`；② 自己加一个开关/内核线/步骤；
> ③ 本地就能验证，不用推上去等 CI 报错。

---

## 1. 一句话理解

工作流 = **"当某件事发生时（on），在什么机器上（runs-on），依次做这些事（steps）"**，
文件放在仓库的 `.github/workflows/` 目录，格式是 YAML。

```
.github/workflows/build.yml      ← 一个文件 = 一个工作流
```

## 2. 最小可跑的例子

```yaml
name: Hello                      # 显示在 Actions 页面的名字
on:
  workflow_dispatch:             # 手动点按钮触发（内核构建最常用）
jobs:                            # 一次运行可以包含多个 job（并行/串行）
  hello:
    runs-on: ubuntu-latest       # 用 GitHub 提供的 Ubuntu 机器
    steps:
      - name: 打招呼             # 步骤名（可省）
        run: echo "hello"
      - name: 用多行脚本
        run: |
          echo "第一行"
          echo "第二行"
```

推送后在仓库 **Actions → Hello → Run workflow** 就能跑。

## 3. 五个核心概念

| 概念 | 作用 | 例子 |
|---|---|---|
| `on` | 触发方式 | `workflow_dispatch`（手动）/ `push` / `schedule`（定时）/ `workflow_call`（被别的流程调用） |
| `jobs` | 一组任务；默认**并行** | `build:`、`plan:` |
| `steps` | job 内的顺序步骤 | 每个 step 要么 `uses:`（用现成 action），要么 `run:`（跑 shell） |
| `runs-on` | 机器 | `ubuntu-latest`（公开仓库免费） |
| `uses` / `run` | 用别人的封装 / 自己写 shell | `uses: actions/checkout@v4` / `run: python -m kbx build` |

## 4. 变量与表达式（最容易搞混的地方）

工作流里有**两套变量**，别混：

| 写法 | 谁解析 | 什么时候 | 例子 |
|---|---|---|---|
| `${{ inputs.kernel }}` | **GitHub** | YAML 渲染时（发给 runner 之前） | `--kernel "${{ inputs.kernel }}"` |
| `$KERNEL` | **shell** | 脚本运行时 | `KERNEL=6.1; echo $KERNEL` |

常见误区：

```yaml
run: |
  echo ${{ inputs.kernel }}      # ✅ GitHub 先替换成 6.1，再交给 shell
  echo $KERNEL                   # ❌ 未定义（除非你在同一个 run 里 export 过）
```

跨步骤传值要用 `env` 或 job outputs：

```yaml
jobs:
  a:
    runs-on: ubuntu-latest
    outputs:
      ver: ${{ steps.s.outputs.ver }}
    steps:
      - id: s
        run: echo "ver=6.1" >> "$GITHUB_OUTPUT"   # ← 注意是 >> 追加，不是 >
  b:
    needs: a
    runs-on: ubuntu-latest
    steps:
      - run: echo "上一步给出 ${{ needs.a.outputs.ver }}"
```

内置的好用变量：`${{ github.sha }}`、`${{ github.run_id }}`、`${{ secrets.XXX }}`、`${{ matrix.* }}`。

## 5. YAML 的四个坑（我们踩过，逐条记下来）

### 坑 1：缩进必须一致

YAML 用缩进表达层级，**同一层必须对齐**（本项目统一用 2 个空格）。

```yaml
steps:
  - name: 对
    run: echo ok
  - name: 错（下面这行多缩进一格，整个工作流会解析失败）
     run: echo bad
```

### 坑 2：`run: |` 块里的**所有**内容都要缩进到块内

```yaml
      - name: 多行脚本
        run: |
          HERE="正确"
          cat <<'EOF'
          这里的每一行也必须缩进到与上面一致
          EOF
```
> 我们的教训：heredoc 的**终止符**（EOF）忘记缩进，整个 workflow 直接无法解析。
> 所以本项目**把长脚本搬进 `.github/scripts/` 或 `kbx/`，workflow 里只写一行调用**。

### 坑 3：别在 YAML 里塞复杂 shell

`run:` 里塞几百行 shell + heredoc + 引号嵌套 = 迟早出错，而且出错信息很难懂。
**推荐**：脚本进仓库，`run: python scripts/xxx.py --arg "${{ inputs.arg }}"`。

### 坑 4：`${{ }}` 里不要写 shell 语法

```yaml
run: echo "${{ inputs.sub_level }}"     # ✅ 只放值
run: echo "$(date)"                     # ✅ 这是 shell 自己解析，写在 run 里没问题
```

## 6. 矩阵：一次跑多条线

```yaml
jobs:
  build:
    strategy:
      fail-fast: false          # 一条失败不影响其它
      max-parallel: 4
      matrix:
        line: ["android12-5.10", "android14-6.1"]
    runs-on: ubuntu-latest
    steps:
      - run: echo "${{ matrix.line }}"
```

矩阵也可以由脚本生成（本项目 `matrix.yml` 就是这样，便于本地单测）：

```yaml
      - id: gen
        run: python .github/scripts/gen_matrix.py --with-612 true >> "$GITHUB_OUTPUT"
  build:
    needs: prepare
    strategy:
      matrix: ${{ fromJSON(needs.prepare.outputs.matrix) }}
    uses: ./.github/workflows/build.yml     # 复用另一个工作流
```

## 7. 复用工作流（`workflow_call`）

`build.yml` 声明 `on: workflow_dispatch` 之外再加 `workflow_call`，
别的流程就能 `uses: ./.github/workflows/build.yml` 并传参，
不用复制粘贴一整份构建逻辑。本项目就是「`build.yml` 干实事 + `matrix.yml` 负责批量调它」。

## 8. 调试技巧

| 想干的事 | 写法 |
|---|---|
| 在界面上看到关键信息 | `echo "## 标题" >> "$GITHUB_STEP_SUMMARY"` |
| 失败也要收产物 | `- uses: actions/upload-artifact@v4` 且加 `if: always()` |
| 让日志分组可折叠 | `echo "::group::标题"` / `echo "::endgroup::"` |
| 让这一步失败但不中断 | `continue-on-error: true` |
| 只在某条件跑 | `if: ${{ inputs.enable_susfs == 'true' }}` |
| 缓存编译加速 | `uses: hendrikmuhs/ccache-action@v1.2` |

## 9. **本地验证**（最重要的一节）

不用推上去就能验：

```bash
python -m unittest discover -s tests      # 逻辑单测
python scripts/check_workflows.py -v      # ① YAML 能否解析 ② 每个 run: 块的 bash 语法
python -m kbx plan --android android14 --kernel 6.1 --sub_level 138 --with susfs,kpm
```

`check_workflows.py` 就是为解决"YAML 看着没问题、其实脚本语法坏了"写的：
它把每个 `run:` 块抽出来，用 `bash -n` 检查语法，CI 与本地跑的是同一套。

想跑完整工作流可选用 [`act`](https://github.com/nektos/act)（本地 Docker 模拟 runner），
但内核构建太重，一般不推荐。

## 10. 在本仓库里加东西的配方

| 想加什么 | 改哪里 |
|---|---|
| 新内核线（如 android16-6.12） | `kbx/refs.py` 的 `KERNEL_LINES` + 同代 SUSFS 表 |
| 新 KSU 版本 | `kbx/refs.py` 的 `KSU_PINS`（含 ref、版本号、同代 SUSFS） |
| 新功能 | 新建 `kbx/features/xxx.py`（继承 `Feature`，实现 `applies/describe/apply`）+ `tests/` 加用例 |
| 新开关 | `.github/workflows/build.yml` 的 `on.workflow_dispatch.inputs` + `kbx/inputs.py` |
| 改刷写流程 | `kbx/packaging.py`（AnyKernel3 与 boot 镜像） |

> 原则：**workflow 只负责"装工具链 + 调用 + 传产物"**，逻辑一律进 Python，
> 这样每一步都能在本地跑单测和 dry-run。
