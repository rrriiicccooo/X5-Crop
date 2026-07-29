# 项目记忆

更新：2026-07-29

这是 X5 Crop 唯一跨会话检查点，只保存当前目标、已验证状态、能力边界、开放风险和精确
下一步。详细运行合同见 `ARCHITECTURE.md`，版本历史见 `CHANGELOG.md`。Git、源码、原始
TIFF、current report、Debug Analysis 与现场命令输出始终优先于本文件。

## 当前检查点

- 分支：`main`。
- Source-core 实现检查点：
  `5f8b96eac9823a6b6c93f5fa208df2e0820a2f02`。本文件由后续 docs-only 提交更新；
  恢复时以现场 `HEAD == origin/main` 为准，不在文档内硬编码自身提交 SHA。
- Tracked 工作区干净；ignored 内容只有 `Test/` 本地样片与证据。
- 当前 runtime：`X5_Crop.py` V4.9 source-core 安全基线。
- 当前用户 runtime 依赖：`numpy`、`tifffile`、`imagecodecs` 与 `Pillow`；SciPy 与
  OpenCV 不是 current runtime dependency。
- 当前稳定公开 Release：`v4.2.8`。
- Runtime schema：

  ```text
  schema_id       = detection_report
  schema_revision = source_core_grid_authority
  ```

- 当前没有获批的独立 `FrameGridEvidence` phase authority。所有需要定位 frame 的输入
  正式得到：

  ```text
  status = needs_review
  reason = frame_grid_authority_unavailable
  frame boxes = ()
  frame TIFF outputs = ()
  ```

这不是 detector 失败后的 fallback，而是 current runtime 的真实能力边界；它不再代表
项目最终成功标准。

## 不可偏移的产品宗旨

X5 Crop 的目标是在用户已经提供 format 与 count 后，自动生成**足够安全、不切掉真实照片
内容**的逐帧 TIFF。它不是照片边界测量工具，不要求唯一还原真实边界，也不追求手术刀式
贴边；合理的 outward over-retention 优于 inward content loss。

固定产品合同：

- 用户输入的 format 与 count 是 runtime authority，detector 不重新猜测这两项。
- Separator、content、outer、expected position、格式尺寸、score 与其它模型线索可以参与
  bounded proposal、assessment 和 selection。Report/Debug 必须区分 observed 与
  inferred，但模型推断本身不是送审理由。
- `approved_auto` 表示最终保护后的输出满足有界安全合同；不表示 Grid phase、separator
  或照片边被唯一证明。
- `needs_review` 只表示存在 protection 无法吸收的具体输出风险，例如整格/ordinal
  歧义、count 无法成立、已知内容仍会被切掉、候选会混入错误相邻照片，或 geometry
  越出 source/lane authority。
- Partial 可以推断真实照片位于哪些 slots；blank 保留 slot；contact/overlap 可以让相邻
  输出框重叠并重复保留共享像素。只有 slot ownership 或安全包络无法有界时才送审。
- 多个精确 geometry 不唯一但输出等价时允许自动批准。回归验收关注 count、顺序、slot
  ownership、真实内容 containment、允许的向外多保留与 TIFF 保真，不要求复刻历史 box。
- `CandidateGate` 只检查候选与输出安全事实；只有 `DecisionGate` 创建 final status 与
  final reasons。

## 当前目标

下一阶段要在上述安全输出合同下，重新评估此前提出的 separator-anchor / model Grid
方案。第一交付物仍是决策完整的设计，而不是立即修改 detector，但它不再要求唯一独立的
真实 Grid phase。

目标数据流的待讨论骨架：

```text
source pixels + authoritative format/count
→ bounded observations and model Grid proposals
→ finite slot hypotheses and assignment
→ conservative per-frame safe crop envelope
→ millimetre output protection / overlap allowance
→ CandidateGate safety facts
→ DecisionGate
→ optional non-blocking Visual Deskew
→ inverse-affine ROI
→ TIFF
```

方案必须保持有限工作量、observed/inferred provenance、source-coordinate geometry、
typed uncertainty 与单向生命周期权限；不得恢复旧 schema、兼容层或按样片写死的
whitelist。Score、expected position、Top-K 或其它选择机制不再被概念性禁止，但只有在
新 current schema 中职责明确、工作量有界且不绕过 Gate 时才能采用。

## 当前运行与状态语义

唯一运行流：

```text
TIFF source pixels
→ base gray / statistics，各一次
→ ScanCanvasEvidence
→ independent long/short scale intervals
→ SourceStripValidationDomain
→ immutable positive-content components
→ FrameGridEvidence(NO_INDEPENDENT_PHASE_AUTHORITY)
→ CandidateGate
→ DecisionGate
→ review copy / current report / Debug Analysis
```

已经成立：

- 设计 aperture 保持离散 format components，不取 hull。
- Long/short scale 分轴传播，TIFF DPI 不参与检测。
- Validation domain 只来自唯一 scan canvas/lane 与 source extent。
- Positive content 由独立 intensity/texture fields、strict 4-connectivity 和 immutable
  RLE 产生；它是确定性 measurement，无 Grid 权限。
- 当前无组合搜索，因此没有 `PhysicalAuditBudget`。

当前未运行：

- Separator 与 photo edge：没有 active detector 或 runtime type。
- Frame Grid：固定 `NO_INDEPENDENT_PHASE_AUTHORITY`。
- Photo containment：`NOT_APPLICABLE_FRAME_GRID_UNAVAILABLE`。
- Visual Deskew：`NOT_APPLICABLE_CORE_UNAVAILABLE`。
- Blank/contact/overlap：没有 current measurement owner，不进入 current schema。
- Millimetre protection：只报告 authority；没有 frame geometry 时 `applied=false`。
- ROI/TIFF exporter：独立 foundation 保留，但 current runtime 没有合法 boxes。

系统只有两个 Gate：

1. `CandidateGate` 检查 source-core facts，不创建 final status/reason。
2. `DecisionGate` 是 final status 与 typed reason 的唯一 owner。

术语：

- `unavailable`：evidence owner 缺少足够权威事实，不是负质量分数。
- `needs_review`：DecisionGate 把阻断 evidence 映射成用户可见 final status。
- `unsolvable`：不是 current runtime/schema 术语，不得作为 alias 加入。
- `contradicted`：只表示完整物理约束明确否定，不能代替 incomplete。

正常 source core 完整但 Grid 缺 authority 时只产生
`frame_grid_authority_unavailable`。若 scan canvas/content 自身不可用，追加各自 typed
reason；被 Grid 阻断的下游只标记 `NOT_APPLICABLE`。

## 已验证检查点

### Current-only tree

- Source-core 原子替换：`0a4a93fcab94cf620cec0bc30b27eeb6f898a48f`。
- 极致收口：`4a5ac722d2a0c489a7da4bd84fbb6adadd3d5254`。
- Runtime 依赖闭合：`5f8b96eac9823a6b6c93f5fa208df2e0820a2f02`；strict
  4-connectivity 改由 NumPy RLE 与确定性 union-find 实现，active runtime 不再依赖
  SciPy。
- Active tree 已原子删除旧 PhotoEdge/separator/sequence/transform/rotated-gray/pixel-bleed
  链及 reader、alias、shim、adapter、feature flag 和双实现。
- 不可达的 auto-approval/Debug PASS、空 export wrapper、重复 content fields 与过期 ignore
  例外也已删除。
- 两轮相同 checklist 均为零残留：无 legacy token、空 source 目录、无 owner module 或
  文档断链。

### Contracts、样片与性能

- Pre-push full：29/29 tests、compileall、14/14 format/mode、shell syntax、diff hygiene
  和 version check 全部通过。
- Named audit：S027、S035、S051、S055、S062、S091、S094、S109、S098 共 9/9 正常
  `needs_review`，0 frame output。S098 只作 `irregular_geometry_stress`。
- 111 张 invariant：111 completed、0 failure、0 frame output。
- NumPy RLE/union-find 在 600 组独立 oracle mask 与 111 张 current 样片上保持 strict
  4-connectivity/content geometry 一致。
- 固定 24 张 detector-only、`--jobs 2`：

  ```text
  cold       单独记录
  median     2.216 秒/张（三次 measured runs）
  ```

  受限环境中 process worker 不可用，实际降级为两个 thread workers；且没有 frame TIFF
  写出，因此只是 `diagnostic_only`。它证明安全基线保有 `<5.0 秒/张`的未来余量，不是
  正式输出性能认证。
- 正式性能仍要求 bounded Grid proposal 与 safe crop envelope 恢复输出后，用固定
  24 张、`--jobs 2`、真实 TIFF 写出和复读，三次中位数 `<=5.0 秒/张`。当前状态必须是
  `not_certified`。
- 人工证据链重新验证：111 条 source manifest、9 条 fit proposal、9 条 user-confirmed
  baseline；outer-noise、overlapping-divider 与 declared-frame-count contracts 均通过。

## 本地证据与历史边界

本地有 111 张未修改 source TIFF：47 张 135/full、14 张 135/partial、32 张
120-66/partial、3 张 120-67/full、10 张 half/full、5 张 half/partial。九张黄金样片的
source/marked/JPG/proposal/baseline hashes 完整保留；八张属于 nominal calibration，
S098 属于 stress。

Baseline 只能在 detector/output receipt 冻结后用于 comparator，不参与检测、Grid、
deskew 或输出选择。

重启前原型证据：

```text
Test/local_audit_evidence/2026-07-29-source-core-cutover/
```

该 ignored 目录含 SHA manifest、cutover patch、原型脚本、决定性输出与 validation
receipt，不得随 cache 清理。它只否定特定表示或 measurement 合同：

- exact top × bottom photo-edge 未在八张 nominal 上形成唯一 pair；
- leading × trailing 笛卡尔积覆盖不完整且超预算；
- 原子暗带、width conservation、section connectivity、dense row-band、
  fragment/K-message、full-axis sparse 与 full-height origin proposal 都没有形成普遍、
  唯一、有限工作量的 separator identity；
- release outer/holder continuity 只能提供 proposal 或向外 containment 线索；
- confirmed-line signal matrix 否定的是
  `base_gray_u8 + current local-noise/integration` 的普遍可用性，不证明原始高位深 TIFF
  没有物理信号。

旧版可借鉴 base gray/statistics 各一次、vectorized measurement、source-coordinate
cache、快速 proposal、模型 Grid、score/rank、事后 comparator、单次 inverse-affine ROI、
固定 cohort 与 Hook 验证。不得原样恢复旧 runtime/schema、format override、
outer-as-photo-edge、width oracle、baseline selection、样片 whitelist 或兼容层；有价值的
概念只能按新的安全输出合同和 current typed owners 重新实现。

## 文档与工作区

- `README.md`：精简中英双语入口。
- `ARCHITECTURE.md`：当前 runtime 与数值合同唯一 owner。
- `CHANGELOG.md`：版本行为、验证边界与历史。
- `docs/user-guide.*`、`docs/quick-start.*`：分离的中英文公共文档。
- `PROJECT_MEMORY.md`：唯一跨会话检查点；不得新增平行 handoff 文档。
- `Test/`：ignored 本地样片与证据。原 TIFF、manual review、baseline 和
  `local_audit_evidence` 必须保留；cache、`.DS_Store` 与 generated output 不保留。

## 开放风险

1. 当前没有 bounded Grid proposal、slot assignment 与 safe crop envelope，所以仍不能
   定位或输出 frame。
2. Containment、protection、blank/contact/overlap 尚无 current runtime 语义。
3. 需要定义哪些 observed/inferred hypotheses 属于同一 slot ownership，以及何时多个
   hypothesis 的 union 会混入错误相邻照片。
4. 需要给 expected-position、anchor count、candidate 数量与搜索预算建立有限合同，避免
   无 expected position 的组合爆炸。
5. XPan 与 120-645 缺少真实 fixture，不能声明准确性覆盖。
6. Detector-only 余量不能代替真实 frame TIFF 性能合同。
7. Green tests、历史 PASS、hash 或 comparator 一致不能单独证明安全输出；Named TIFF
   必须检查真实内容 containment，但不要求精确贴合人工边界。

## 新任务的精确下一步

新任务的第一交付物是重新审阅此前提出的 separator-anchor / model Grid 方案，并按“安全
输出而非唯一边界真值”形成一份决策完整的方案。此阶段不是立即修改 tracked detector。

开始时核对：

```bash
git log -1 --oneline --decorate
git status --short
git rev-parse origin/main
rg 'REPORT_SCHEMA_REVISION' x5crop
python3 -B Test/manual_review/red_markup_converter.py verify
wc -l Test/manual_review/manifest.jsonl
wc -l Test/manual_review/user_confirmed_golden_baseline.jsonl
```

方案必须一次锁定：

1. 用户 format/count authority 与 Grid proposal 的唯一 current owners；
2. observed separator anchors、expected position、格式尺寸、content/outer clues 与 inferred
   positions 如何进入有限 proposal、assessment 和 selection；
3. anchor count 不同、无 separator、full/partial、horizontal/vertical、dual-lane 的
   candidate domain 与 bounded work；
4. ordinal、slot ownership、blank、contact、overlap 与 per-frame safe crop envelope；
5. 多个 hypotheses 何时输出等价、如何 union/overlap，以及何时 protection 无法吸收而必须
   review；
6. CandidateGate safety checks 与 DecisionGate 的唯一 final status/reason 映射；
7. source-coordinate geometry、typed uncertainty、optional deskew 与 inverse-affine output；
8. PASS/review cohort、九张人工 baseline、S098 stress、24 张真实输出和 111 张验证合同；
9. current-only tree 的保留、增加与原子删除清单。

获得用户明确批准前，不修改 tracked detector，不恢复旧 detector/compatibility，不让
任何 lower layer 绕过两级 Gate，也不声明自动裁切或正式输出性能已经通过。

新任务恢复提示：

> 继续 X5 Crop。读取 `README.md`、`AGENTS.md`、`PROJECT_MEMORY.md` 与
> `ARCHITECTURE.md`，核对 `main` 与 `origin/main` 一致、tracked 工作区干净，并确认
> `5f8b96ea` 是 source-core 实现检查点。当前 runtime 仍是 review-only，但产品宗旨是
> 在用户提供 format/count 后保守自动裁切、不切真实内容，而不是唯一证明照片边界。
> 重新审阅此前的 separator-anchor / model Grid 方案，先形成 bounded proposal、safe crop
> envelope、partial/blank/overlap 与两级 Gate 的决策完整设计；不要先修改 tracked
> detector，也不要原样恢复旧 runtime/schema。
