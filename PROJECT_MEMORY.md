# 项目记忆

更新：2026-07-29

这是 X5 Crop 唯一跨会话检查点，只保存当前目标、已验证状态、能力边界、开放风险和精确
下一步。详细运行合同见 `ARCHITECTURE.md`，版本历史见 `CHANGELOG.md`。Git、源码、原始
TIFF、current report、Debug Analysis 与现场命令输出始终优先于本文件。

## 当前检查点

- 分支：`main`。
- Source-core 实现检查点：
  `4a5ac722d2a0c489a7da4bd84fbb6adadd3d5254`。本文件由后续 docs-only 提交更新；
  恢复时以现场 `HEAD == origin/main` 为准，不在文档内硬编码自身提交 SHA。
- Tracked 工作区干净；ignored 内容只有 `Test/` 本地样片与证据。
- 当前 runtime：`X5_Crop.py` V4.9 source-core 安全基线。
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

这不是 detector 失败后的 fallback，而是 current runtime 的真实能力边界。

## 当前目标

下一阶段要找到并证明一个**独立的 Frame Grid phase authority**。只有它成立后，系统才
有资格继续建立 frame slots、逐帧照片 containment 和自动输出。

目标数据流：

```text
source pixels
→ 独立 Grid phase authority
→ finite frame slots
→ per-frame positive content + design height + lane authority
→ shared safe containment
→ millimetre output protection
→ optional non-blocking Visual Deskew
→ inverse-affine ROI
→ TIFF
```

固定约束：

- Grid authority 必须物理独立、可审计，并传播完整 uncertainty。
- Separator、photo edge、outer、positive content、设计宽度或 baseline 都不能单独补出
  Grid phase。
- Content 只能验证或否定已有 slot，不能创建 phase、ordinal 或 separator identity。
- Protection 与 Visual Deskew 都是后置消费者，不能选择核心 geometry。
- 缺少权威证据时继续 `needs_review`；不得恢复 score、Top-K、retry、fallback、样片规则
  或 compatibility layer。
- 新 authority 一旦获批，应作为一次决策完整的实施套餐；普通工程修复不再拆成连续
  微型审批。

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
- Active tree 已原子删除旧 PhotoEdge/separator/sequence/transform/rotated-gray/pixel-bleed
  链及 reader、alias、shim、adapter、feature flag 和双实现。
- 不可达的 auto-approval/Debug PASS、空 export wrapper、重复 content fields 与过期 ignore
  例外也已删除。
- 两轮相同 checklist 均为零残留：无 legacy token、空 source 目录、无 owner module 或
  文档断链。

### Contracts、样片与性能

- Pre-push full：26/26 tests、compileall、14/14 format/mode、shell syntax、diff hygiene
  和 version check 全部通过。
- Named audit：S027、S035、S051、S055、S062、S091、S094、S109、S098 共 9/9 正常
  `needs_review`，0 frame output。S098 只作 `irregular_geometry_stress`。
- 111 张 invariant：111 completed、0 failure、0 frame output。
- 固定 24 张 detector-only、`--jobs 2`：

  ```text
  cold       1.797 秒/张
  measured   1.801 / 1.807 / 1.816 秒/张
  median     1.807 秒/张
  ```

  受限环境中 process worker 不可用，实际降级为两个 thread workers；且没有 frame TIFF
  写出，因此只是 `diagnostic_only`。它证明安全基线保有 `<5.0 秒/张`的未来余量，不是
  正式输出性能认证。
- 正式性能仍要求独立 Grid authority 恢复输出后，用固定 24 张、`--jobs 2`、真实 TIFF
  写出和复读，三次中位数 `<=5.0 秒/张`。当前状态必须是 `not_certified`。
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

旧版只借鉴计算与工程纪律：base gray/statistics 各一次、vectorized measurement、
source-coordinate cache、快速 proposal、事后 comparator、单次 inverse-affine ROI、
固定 cohort 与 Hook 验证。不得恢复 score/rank/Top-K/retry/format override/candidate cap、
outer-as-photo-edge、width oracle、baseline selection 或兼容层。

## 文档与工作区

- `README.md`：精简中英双语入口。
- `ARCHITECTURE.md`：当前 runtime 与数值合同唯一 owner。
- `CHANGELOG.md`：版本行为、验证边界与历史。
- `docs/user-guide.*`、`docs/quick-start.*`：分离的中英文公共文档。
- `PROJECT_MEMORY.md`：唯一跨会话检查点；不得新增平行 handoff 文档。
- `Test/`：ignored 本地样片与证据。原 TIFF、manual review、baseline 和
  `local_audit_evidence` 必须保留；cache、`.DS_Store` 与 generated output 不保留。

## 开放风险

1. 没有独立 Grid phase authority，当前不能定位 frame。
2. 没有 frame assignment，containment、protection、deskew、blank/contact/overlap 尚无
   runtime 语义。
3. Positive content 无权提供 phase。
4. 若重新研究 separator，必须先提出新的独立 source evidence owner，不能继续优化已
   终局失败的 proposal/fragment 图。
5. XPan 与 120-645 缺少真实 fixture，不能声明准确性覆盖。
6. Detector-only 余量不能代替真实 frame TIFF 性能合同。
7. Green tests、PASS、hash 或 comparator 一致不能代替原 TIFF 坐标中的物理确认。

## 新任务的精确下一步

新任务的第一交付物是一份**决策完整的独立 Grid phase authority 方案**，不是另一个零散
separator 微型原型，也不是立即修改 tracked detector。

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

1. authority 的独立物理来源、唯一 owner 与 provenance；
2. 它为何不消费 separator、content、baseline 或待证明 geometry；
3. source-coordinate measurement、完整 uncertainty 与多 component 行为；
4. full/partial、horizontal/vertical、dual-lane 和缺 fixture format 的 capability；
5. Grid/ordinal/slot/content assignment/per-frame containment 的单向权限；
6. `unavailable`、`contradicted`、`needs_review` 与 finalization 的关系；
7. bounded work、Named TIFF、S098、24 张真实输出和 111 张 invariant 合同；
8. current-only tree 的保留、增加与原子删除清单；
9. 普通工程问题在同一授权内修复，只有改变物理 authority 或扩大范围才重新询问。

获得用户明确批准前，不修改 tracked detector，不恢复旧 detector/compatibility，不让
Grid、content、outer、protection 或 deskew 反向授权，也不声明自动裁切、deskew 物理
精度或正式输出性能通过。

新任务恢复提示：

> 继续 X5 Crop。读取 `README.md`、`AGENTS.md`、`PROJECT_MEMORY.md` 与
> `ARCHITECTURE.md`，核对 `main` 与 `origin/main` 一致、tracked 工作区干净，并确认
> `4a5ac72` 是 source-core 实现检查点。当前是 review-only source-core 安全基线，唯一
> 核心缺口是独立 Frame Grid phase authority。先提交一份决策完整、无循环证据、有限
> 工作量、current-only 的 authority 方案；不要恢复 separator/photo-edge/outer 旧
> detector，不要先修改 tracked 文件。
