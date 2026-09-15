# Codex 协作规则

本文件只保存长期协作政策。当前架构见
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)，版本变化见
[docs/CHANGELOG.md](docs/CHANGELOG.md)，当前任务见按需读取的
[docs/PROJECT_MEMORY.md](docs/PROJECT_MEMORY.md)。

## 开始工作

1. 首次进入项目或需要确认产品入口时阅读 `README.md`；其余按本次任务读取相关文档与源码。
   只有用户明确要求恢复、更新或交接时才读取 `docs/PROJECT_MEMORY.md`。
2. 检查当前分支和工作树：

   ```bash
   git branch --show-current
   git status --short
   ```

3. 以现场 Git、源码、原 TIFF、current report、Debug Analysis 和最新命令输出为准；历史计划、
   记忆与旧 receipt 只作线索。

GitHub 是 tracked 源码与文档的权威来源。NAS 和复制目录只用于传输或测试。
首次 clone 运行 `tools/git/install_hooks.sh`，启用仓库中的 `.githooks`。

## 子代理调度

以下原则适用于所有 subagent；主 Agent 负责拆解任务、保持主任务目标不变，并验收结果：

- 架构决策、需求歧义、跨模块根因分析、最终质量判断，以及影响 reference 权限、物理模型、Gate、
  黄金结论或发布资格的判断由主 Agent 负责。可以并行收集只读证据，但不得仅为节省时间或额度
  把最终判断交给较弱模型。
- 只在子任务体量较大、相互独立，且预期并行收益超过上下文传递与结果整合成本时派发。按任务选择角色：
  `explorer` 回答具体代码问题，`luna_worker` 处理边界清楚且可机械验收的执行任务，复杂独立实现使用
  能力相称的 worker；几分钟内能够完成的轻量任务留在主线程。
- 每个 worker 的任务描述必须上下文完整，明确文件范围、任务边界、预期输出和可核验的验收
  标准；worker 不得修改主任务目标或自行扩大范围。
- 只读任务可以并行。涉及文件写入的 worker 必须使用独立 worktree；无法隔离时改为串行，
  避免多个任务同时修改同一工作树。
- worker 完成后，主线程必须按预先给出的验收标准检查结果。首次未达标时提供具体反馈并定向修正；
  反复失败、边界不清或需要跨模块判断时由主 Agent 接管，不无限重派，也不把未验收结果视为完成。
- 如果多个 worker 无法并行，检查 `~/.codex/config.toml` 中的
  `agents.max_concurrent_threads_per_session` 是否被设置为 `1`，并检查当前会话的并发槽位与运行时限制。

## 长时间异步工作

- 长时间任务优先使用完成事件通知或长轮询；仅在出现新输出、状态变化或需要交互时处理进展，
  避免为确认“仍在运行”而频繁轮询。
- 等待参数按当前工具允许范围、预计任务时长与交互需要设置；嵌套等待遵循当前工具的超时与
  提前返回语义，及时响应用户输入。

## Codex 图像查看与传输

- 禁止在同一请求中批量传入原始 TIFF 或 full-resolution review JPG。
- 原图查看必须一次一张；不得并行调用多个图像查看工具。
- 多图比较优先使用现有 `--debug-analysis` 生成的 1800px 诊断 JPG，或使用临时的有界预览
  副本；当前 Codex 使用不超过 20 MB/张作为保守阈值。
- 预览图只能作为视觉上下文，不能替代或修改原始 TIFF、用户确认的 review JPG、坐标数据或
  黄金基线，也不能作为几何准确性的权威证据。
- 如果图像查看触发 reconnect 或 `stream disconnected before completion`，立即停止重复重试，
  减少图像数量或尺寸后再试，并记录发生时间；同时将代理、睡眠、网络切换等问题与 X5-Crop
  运行逻辑分开排查。

## 用户可见交付物

- 面向用户的 UI、PDF、PPT、报告、截图与导出文件直接服务产品或业务目标，以直接、肯定的产品
  语言呈现功能、结果、必要限制和操作指引。Review 原因、证据不足、误差预算与操作提示属于
  产品必要信息，按当前产品合同呈现。
- Agent 的工作计划、实现过程与自我说明放在协作回复、代码注释、PR/MR 描述或现有职责对应的
  内部文档中。
- 用户明确要求在交付物中展示设计说明、方法论、实现过程或工作记录时，按该交付目标组织内容。

## 文档职责

| 文件 | 唯一职责 | 语言 |
|---|---|---|
| `README.md` | GitHub 简短入口与语言选择 | 精简中英双语 |
| `docs/user-guide.zh-CN.md` | V5 中文完整手册（发布前为开发预览） | 中文 |
| `docs/user-guide.en.md` | V5 English user guide (development preview before release) | English |
| `docs/quick-start.zh-CN.md` | V5 中文快速启动（发布前为开发预览） | 中文 |
| `docs/quick-start.en.md` | V5 English quick start (development preview before release) | English |
| `docs/ARCHITECTURE.md` | 已确认的 V5 合同、运行流、数值合同与源码 owner | 中文 |
| `docs/MANUAL_ANNOTATION.md` | 本地黄金基线标注器的使用与权限边界 | 中文 |
| `docs/CHANGELOG.md` | 版本级行为与验证边界 | 中文 |
| `docs/PROJECT_MEMORY.md` | 当前目标、证据边界、风险与下一步 | 中文 |
| `AGENTS.md` | 长期协作政策 | 中文 |

- 内部文档只写中文正文，保留必要的英文标识、命令和 schema 名。
- 用户可见行为变化必须同步更新中英文公共文档。
- 不复制架构、版本历史或当前任务状态；链接到唯一 owner。
- 除 `README.md`、`AGENTS.md` 与 `LICENSE` 外，实质性文档只放在 `docs/`。
- 文档保持当前、简洁、专业；不写执行流水账、聊天记录或过期计划。

## 项目记忆与 reference 权限

- `docs/PROJECT_MEMORY.md` 是唯一跨会话检查点；不建立 `SESSION_HANDOFF.md`、
  `NEXT_ACTIONS.md`、`DECISIONS.md` 或同类文件。
- 只在用户明确要求时读写，并只保留当前目标、已验证事实、开放风险和精确下一步。
- 人工 reference 的 authority、黄金几何语义与 source-SHA 绑定只由 `docs/ARCHITECTURE.md` 第 14 节和
  `docs/MANUAL_ANNOTATION.md` 定义。只有用户在原图坐标中直接确认的边界或独立外部测量可以成为
  reference；自动工具和模型只能产生 proposal。不得让模型查看完整长 TIFF 后代写 reference，歧义保持
  unresolved。

## 架构与实现协作

- 仓库只有一条 V5 current-only production path；V5 直接在 `main` 开发。除非用户明确恢复，不开发
  历史 app、native packaging、兼容入口或平行 runtime。
- `docs/ARCHITECTURE.md` 是产品合同、运行流、数值合同、工作量上限、验证语义与源码 owner 的唯一
  说明。修改 detector、placement、Gate、输出、report、TIFF I/O、性能或黄金比较前，读取相关章节和
  当前源码；`AGENTS.md` 不复制这些合同。行为变化更新该唯一 owner、`docs/CHANGELOG.md` 和受影响的
  中英文公共文档。
- 项目规则和用户指令优先于通用 skill。通用调试、简化或验证方法不得改变 format/count authority、
  reference 权限、typed evidence、自动批准边界或发布标准；精确语义以架构文档为准。
- 修复聚焦用户要求范围内的根因，并在同一机制内删除已被替代的路径；不得借“彻底修复”扩大到无关
  清理。删除稳定版曾对真实样片有效的机制前，先从对应 tag 确认其物理作用，并将有效事实迁入架构文档
  指定的 current owner，或用黄金反例证明其不安全且已被现机制覆盖。
- 不新增样片特例、白名单、格式 denylist、无法解释的 fallback 或仅为提高覆盖率而放宽的权限。新增
  自由度、依赖、并发或性能行为必须先满足架构文档中的 authority、工作量、反例、Gate 与验证合同。

## 验证

- 本机依赖库升级后，以现场新版为准：核对实际加载版本，更新 `tools/install/dependencies.toml`
  和受影响检查，再做相称验证。保留本机新版，不为满足旧合同或旧 receipt 降级共享依赖。
  临时环境路径和历史版本记录不能替代实际 import 版本核验。

`tools/verify` 是唯一验证入口：

```text
staged | full | accuracy | diagnostic | performance |
platform | platform-check | platform-package | pre-push
```

- Hook、CI、Windows `.bat` 与 Intel `.command` 只能薄调用该入口，不复制验证逻辑。
- `.githooks/pre-commit` 运行 staged hygiene；`.githooks/pre-push` 根据实际 commit range 选择
  documentation 或 full。纯 Markdown 使用 documentation；其余改动和无法识别的范围使用 full。
  不得使用 `--no-verify`。
- Commit 或 push 前不手工重复运行即将由对应 Hook 覆盖的同一验证。只有 Hook 未覆盖的专项检查，或
  为诊断已经出现的失败，才额外手工运行；最终以正常 Hook 结果为准。
- 验证应与本次改动和声明相称：先运行能证明目标的最小专项检查；只有依赖范围、失败证据、项目 Gate
  或待提交内容要求时才扩大。一次成功且其输入未变化的检查不重复运行，也不以通用 skill 强制增加
  release 或 performance 验证。
- Development gold、diagnostic、accuracy、performance、platform、cohort、source SHA、count、proposal、
  candidate、decision 与 release threshold 的全部精确语义由 `docs/ARCHITECTURE.md` 第 14 节定义；标注器
  权限与工作集布局由 `docs/MANUAL_ANNOTATION.md` 定义。此处只保存命令路由，不复制数值或状态合同。
- `Test/` 不受 Git 跟踪；不得提交原始 TIFF、生成输出或 receipt。Named-TIFF 与端到端验证必须调用正式
  CLI 和完整 detection flow，测试工具不得提供更容易通过的 detector path。

## Git、完成与发布

- 实现任务在已授权范围内持续完成实现、相关验证、受影响文档与下述 Git 交付，并修复本次改动
  引入的失败；用户明确要求阶段性检查时按该边界交付。只读审核以有证据的结论交付完成。
- 已授权范围内的执行与验证直接推进；需要用户决定的新产品选择、reference 确认或发布授权时，
  完成不依赖该决定的工作，并说明具体待决事项。
- 保留用户和其它任务的修改；没有明确许可不得 reset、restore 或删除未知文件。
- 使用 `rg` 搜索；不可用时再用下一种工具。文件编辑使用 `apply_patch`。
- Commit 前核对 staged 与 unstaged diff。除非用户明确禁止，tracked 变更应提交并由正常 Hook
  推送当前 `main`。
- 不提交 `.venv/`、`build/`、`dist/`、`release/`、cache、`.DS_Store`、`Test/`、
  `x5_crop_output/` 或大 TIFF；除非用户明确批准 Git LFS fixture。
- `LICENSE` 由 GitHub tracked tree 与 Release 包保存；本地工作区使用 non-cone sparse checkout
  排除它，README 与公共手册直接链接 GitHub。发布构建仅在确认该路径带 Git `skip-worktree` 时从
  当前 `HEAD` 读取同一字节写入临时包；不得因此把文件恢复到本地工作区或掩盖其它缺失发布源。
- `tools/release/manifest.py` 是发布内容唯一 owner。用户包不包含 modular source、tests、tools、
  fixtures、内部文档、开发依赖或生成输出。
- 构建命令为 `python3 -m tools.release.build --version <version>`。Release 内容由
  `tools/release/manifest.py` 独占，资格、目标平台、receipt 与未覆盖范围的精确合同只以
  `docs/ARCHITECTURE.md` 第 14 节为准；全部要求绑定同一 release commit 前，不创建 RC、tag、
  GitHub Release 或公开 ZIP。
