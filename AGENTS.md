# Codex 协作规则

本文件只保存简短且强制的仓库政策：文档职责、实现边界、验证、发布和交接规则。
架构、历史与当前任务状态由各自唯一文档负责。

## 开始工作

1. 编辑前阅读根 `README.md`。只有用户明确恢复、更新或请求跨会话交接时，才读取
   `PROJECT_MEMORY.md`。
2. 核对当前分支与工作树：

   ```bash
   git branch --show-current
   git status --short
   ```

3. GitHub 是受跟踪源码与文档的权威来源；NAS 和复制目录只用于传输或测试。

仓库：

```text
git@github.com:rrriiicccooo/X5-Crop.git
https://github.com/rrriiicccooo/X5-Crop
```

## 文档职责与语言

| 文件 | 唯一职责 | 语言 |
|---|---|---|
| `README.md` | GitHub 简短入口与语言选择 | 精简中英双语 |
| `docs/user-guide.zh-CN.md` | 中文完整用户手册 | 中文 |
| `docs/user-guide.en.md` | 英文完整用户手册 | English |
| `docs/quick-start.zh-CN.md` | 中文发布版快速启动 | 中文 |
| `docs/quick-start.en.md` | 英文发布版快速启动 | English |
| `ARCHITECTURE.md` | 当前运行流、数值合同与源码分层 | 中文 |
| `CHANGELOG.md` | 版本级行为、验证边界与回滚背景 | 中文 |
| `PROJECT_MEMORY.md` | 按需读取的唯一跨会话检查点 | 中文 |
| `AGENTS.md` | 长期协作政策 | 中文 |

- 内部文档只写中文正文，保留必要的英文标识、类型名、命令与 schema 名。
- 公共中英文文档按语言分开，不在同一文件逐段重复。
- 默认不读取英文公共文档；只有英文文档、发布或对应事实校验任务才读取。
- 用户可见的设置、用法、启动器、输出或发布包变化，必须在同一变更中更新两种公共语言。
- 不复制长篇说明；链接到唯一 owner。文档必须简洁、专业、当前且互不重叠。
- 根 `ARCHITECTURE.md` 是唯一架构文档；`docs/` 只保存公共用户文档，不建立架构镜像。

## 交接与项目记忆

- `PROJECT_MEMORY.md` 是唯一跨会话交接；不得创建 `SESSION_HANDOFF.md`、
  `NEXT_ACTIONS.md`、`DECISIONS.md` 或同类平行文件。
- 仅在用户明确恢复、请求交接或要求更新项目记忆时读写。
- 只保留当前目标、已验证检查点、验证边界、开放风险和精确下一步。架构与历史留在各自
  owner。
- Git、源码、原 TIFF、current report、Debug Analysis 和现场命令输出始终优先于记忆。
- 人工审阅重新开始时，先定义唯一 current schema；不恢复或迁移旧标签、candidate ID、
  决策或 runtime 白名单。
- 不得让模型查看完整长 TIFF 后代写 reference 边界。Baseline 只能来自绑定 source SHA
  的原图坐标，并由用户直接点击后明确确认，或来自独立校准的外部测量。OpenCV、SciPy、
  X5 Crop、模型视觉、生成 JPG 和算法一致只能产生非权威 proposal；reference 真值歧义
  保持 unresolved。该限制只约束 baseline 权限，不禁止 runtime 使用模型推断产生保守安全
  输出。

## 当前范围

- 当前入口：`X5_Crop.py` V4.9。
- 当前稳定 GitHub Release：`v4.2.8`。
- 开发源码位于 `x5crop/`；Release 可嵌入为单文件 `X5_Crop.py`。
- 除非用户明确恢复 app 或 native packaging，只处理 standalone X5 Crop workflow。
- 当前任务和人工审阅状态只保存在 `PROJECT_MEMORY.md`。

## 产品宗旨与批准语义

- X5 Crop 的目标是在用户已经提供 format 与 count 后，自动生成**足够安全且不切掉真实照片
  内容**的裁切；不是唯一还原或测量真实物理边界，也不追求手术刀式精度。
- 用户提供的 format 与 count 是 runtime authority。Detector 不重新猜测这两项，只在其
  约束内建立有限 Grid proposal、slot assignment 与输出。
- Separator、content、outer、expected position、格式尺寸、score 与其它模型线索都可以
  参与 proposal、assessment 和 selection。必须在 report/debug 中区分 observed 与
  inferred，但“属于推断”本身不是 `needs_review` 理由。
- `approved_auto` 只表示最终保护后的输出满足有界安全合同；不表示每条照片边、separator
  或 Grid phase 都被唯一证明，也不保证每张输出只含本 slot 的像素。固定 protection 与
  bounded contact/overlap 可以跨过 nominal divider、带入相邻照片像素并让相邻输出重叠。
- `needs_review` 只用于具体且无法由 protection 吸收的输出风险，例如整格/ordinal 歧义、
  请求 count 无法成立、主照片的 slot ownership 无法有界、已观测内容仍会被切掉，或未保护
  geometry 越出 source/lane authority。不得把 protection/shared interval 内出现邻片像素
  当作 ownership 失败，也不得只因 separator 缺失、照片为空、精确边界未观测或多个候选在
  输出上等价而送审。
- Partial 可以推断实际照片位于哪些 slot；blank 保留 slot；contact/overlap 优先允许输出框
  重叠以保全内容。只有 slot ownership 或安全包络无法有界时才送审。
- 回归验收关注 format/count、顺序、slot ownership、真实内容 containment 与 TIFF 保真；
  不要求复刻历史 box，也不把贴近人工边界本身当作质量目标。

## 长期实现规则

- 除非用户明确改变要求，保持 TIFF 位深、通道结构、ICC/色彩空间、resolution、
  metadata 与已知无损压缩行为。
- 结构清理不需要保持历史 PASS/REVIEW、geometry、confidence、reason、schema、debug
  或 cache parity；优先当前安全输出合同。
- 结构闭合后才用真实样片校准 detection。不得为单个文件普遍放宽规则；必须复查已知
  正常格式，尤其是 `135`。
- Named-TIFF 与端到端回归必须运行完整 detection flow，包括 scan-canvas matching、
  Grid proposal、safe containment 与 transform assessment。纯 solver 单测可显式构造
  typed `DetectionWorkspace` fixture；production runtime 不得 bypass。
- 照片尺寸只属于 `FramePhysicalSpec`；片夹扫描画布只属于
  `ScanCanvasPhysicalSpec` catalog。TIFF resolution 只作 I/O metadata，不得进入检测
  尺度、证据或决策。
- 方向性需求以水平片条措辞为基准，同时实现旋转等价的垂直行为。
- Runtime flow 或 source layering 变化更新 `ARCHITECTURE.md`；版本行为、打包、验证或
  回滚变化更新 `CHANGELOG.md`。

## 极致干净合同

- 每个 active concept 只有一个 canonical name、type、owner 和真相来源。
- 权限只沿 proposal、build、evidence、assessment、selection、decision、
  finalization、output、report、debug 单向流动。
- `CandidateGate` 和 `DecisionGate` 是仅有的两个 Gate；只有 `DecisionGate` 创建 final
  status 与 final reasons。
- Format spec、adaptive measurement、runtime configuration 和 report description
  保持分离。配置只在 runtime boundary 解析；lower layer 接收显式 typed input，不查询
  registry 或发明默认值。
- Foundation code 只知道 geometry、pixels、TIFF I/O、cache mechanics 与 units，不知道
  format identity、decision state 或 report schema。
- Runtime、tests、tools、report 与 debug 只消费 current schema。Report 是审计产物，
  不是 detection cache；只缓存精确且与 count/offset 无关的 measurement。
- 被替代的 API、字段、alias、import、reducer、shim、test 和兼容分支必须同批删除。
- 不保留 dead file、unreachable helper、pass-through wrapper、重复 model、隐藏 decision
  constant，或只搬运复杂度的 abstraction。
- 只有消除真实重复或职责歧义时才增加 abstraction；名称必须表达物理事实或生命周期职责。
- 代码、contract tests、`ARCHITECTURE.md`、current reports 与 Debug Analysis 必须描述
  同一系统。
- 每发现一类残留，先增加能失败的 contract，再删除整类残留并保留 contract。
- 架构清理只有在 full verifier 通过，且同一冻结 checklist 连续两次只读审计无已知问题后
  才闭合。只有明确 contract violation、无法表达的物理事实或真正不兼容能力才能重新打开。

## 检测与性能

- Search hint、blank appearance、重复宽度与 expected position 不是物理真值，但可以作为
  bounded proposal/selection 输入。精确边界可以保持 inferred/unresolved；只要最终
  safe crop envelope 已有界，便不阻止自动批准。
- Early-stop 只来自 resolved output-safety assessment，而不是精确边界证明。预算耗尽表示
  safety assessment unavailable，不能成为 reliability evidence；candidate 与 final
  decision 权限分离。
- 优化前固定一个真实样片，记录 wall/detection time、candidate builds、重复 measurement
  与真实 call-stack hotspot。
- 只缓存带 typed key 的精确 count/offset-independent measurement；不缓存 candidate、
  Gate、decision、final reason 或近似 geometry。
- 每轮优化后复测同一样片，再运行 contracts、代表性 format/mode、current-schema
  validation，并人工检查 Debug Analysis。输出差异是校准证据，不是历史 parity gate。

## 验证

`tools/verify` 是唯一可执行验证入口；Hook 与 CI 只能薄调用，不能复制命令。

- `.githooks/pre-commit` 通过 `tools/verify staged` 负责 staged hygiene。
- `.githooks/pre-push` 通过 `tools/verify pre-push` 负责最终 full validation。
- 正常 commit-and-push 流程中，同一棵 tree、同一 scope 只验证一次。不要在 `git push`
  前手工重复 `tools/verify full`；成功的 pre-push Hook 是唯一最终完整验证。
- 只有不准备 push，或需要 full 输出排障时才手工运行：

  ```bash
  tools/verify full
  ```

- 验证后 tree 变化，旧结果立即失效。
- Detection 变化应比较 current-schema report：

  ```bash
  python3 -m tools.regression.compare <baseline> <candidate>
  ```

- 至少检查 transform outcome/source、mapped shared short axes、lane divider mapping、
  status/reasons、selected rank、geometry resolution、crop envelopes 与 final boxes。
- `Test/` fixture 未受跟踪，其目录布局不是源码合同。验证时动态发现 TIFF：

  ```bash
  find Test -type f \( -iname '*.tif' -o -iname '*.tiff' \) | sort
  ```

- 当前 111 条 source manifest 的验收期望已由用户明确确认：绑定同一 source SHA 的
  `pass_*` 共 88 条，必须得到 `approved_auto`，包括 S098；`unknown_*` 共 23 条，在
  CandidateGate 有具体阻断事实时允许 `needs_review`，否则优先 `approved_auto`。该映射
  只进入 validation-only cohort，不能成为 detector 输入、runtime whitelist 或
  DecisionGate 之外的状态权限。
- 现有真实样片可以校准 search prior 与 measurement，但样片覆盖不完整。经验分布不得变成
  “未见过即失败”的硬边界；coverage gap 只限制验证或发布声明，不得单独制造
  `needs_review`。XPan 与 120-645 暂无且短期不补真实 fixture，不得把补样片设为实现
  blocker，也不得建立格式级 denylist。
- 样片可用时覆盖代表性 `135/full`、`120-66/partial`、`half/full` 与 `120-67/full`。
  Unit tests 通过不证明 named-TIFF 安全裁切；完成声明前必须检查 current reports、Debug
  Analysis 与输出是否存在真实内容 inward loss。

## 完成与同步

- 每个 clone 运行一次 `tools/git/install_hooks.sh`，不得使用 `--no-verify`。
- Codex 修改 tracked source、docs、configuration、launcher 或 release metadata 后，
  除非用户明确禁止，应提交并推送当前分支；依赖已启用 Hook，不重复手工验证。
- Commit 前确认 staged 与 unstaged 变化均为预期。失败时报告 blocker 并保留最安全状态。

## Git 与本地文件

- 保留用户和其它 session 的修改；没有明确许可不得 reset 或 restore。
- `.gitignore`、`.github/`、`tools/` 与 `install/` 必须可见。
- 除 `LICENSE` 外，当前 tracked tree 完整可见。`LICENSE` 由 GitHub 保存，在本地 sparse
  checkout 中排除。历史源码只保存在 Git history 与 tags，不维护 `archive/`。
- 预期本地 sparse checkout：

  ```text
  /*
  !/LICENSE
  ```

- 用户明确要求干净交接时，在最终 Hook push 后再次删除 ignored cache、compiled bytecode、
  Finder metadata 与 generated output。
- 不提交 `.venv/`、`.venv-build/`、`build/`、`dist/`、`release/`、cache、`.DS_Store`、
  `downloaded_apps/`、`Test/`、生成的 `x5_crop_output/` 或大 TIFF；除非用户明确批准其
  作为 Git LFS fixture。

## 发布包

- `tools/release/manifest.py` 是 package content 的唯一 owner。
- 使用 `python3 -m tools.release.build --version <version>` 构建用户 ZIP。
- Builder 必须生成 standalone script，只打包 manifest entries，保持 launcher executable，
  并使用 Python `zipfile` 保存中文文件名的 UTF-8 metadata。
- 发布包分别提供中文与英文用户手册、快速启动，不使用逐段中英混排文档。
- 用户包不包含 modular source、tests、内部文档、diagnostics launcher、本地样片或 generated
  output。
- macOS 只准备当前 Release folder：标记主 launcher 与 installer executable，并在可用时
  移除 quarantine attribute；不得建立永久 system-wide trust。
