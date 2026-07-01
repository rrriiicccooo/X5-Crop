# X5 Crop 架构说明 / Architecture Guide

这份文档是 X5 Crop 的开发者架构地图。它说明当前源码怎么分层、
policy 如何拥有行为开关、哪些能力可以通用化、哪些 format / mode
规则必须继续隔离。

This document is the developer architecture map for X5 Crop. It explains the
current source layout, how policy owns behavior switches, which capabilities can
be shared, and which format / mode rules must remain isolated.

根目录的 `ARCHITECTURE.md` 和 `docs/ARCHITECTURE.md` 内容保持一致：
根目录版本方便在 GitHub 首页发现，`docs/` 版本保留给已有开发链接使用。

The root `ARCHITECTURE.md` and `docs/ARCHITECTURE.md` are kept in sync. The root
copy is easier to discover on GitHub, while the `docs/` copy preserves existing
developer links.

## 中文说明

### 文档定位

- `README.md` 和 `快速启动_Quick_Start.md` 面向普通用户和 Release 使用。
- `CHANGELOG.md` 记录版本变化、验证结果和回滚线索。
- `AGENTS.md` 保留 Codex 协作规则、当前 handoff 和回归优先级。
- `ARCHITECTURE.md` 面向继续开发的人，记录源码层级、policy 边界和迁移方向。

### 当前目标

V4.7 是一次 clean-room source rewrite。目标不是调检测阈值，也不是改变裁切结果，
而是在保持 V4.5.4 golden 输出行为的前提下，让 active source 只通过真实职责模块工作。

核心原则：

- 以 V4.5.4 `Test/` 报告作为行为 baseline。
- 所有 refactor 都应先追求核心字段 0 diff。
- policy surface 可以通用化，默认行为不能随便推广。
- `120-66` dark-band / square-frame 风险模型必须隔离。
- weak `grid`、`equal` 或 content-only 证据不能因为结构清理获得自动 PASS 权限。
- TIFF metadata、位深、ICC / resolution、compression 行为属于公开契约，不应被架构整理改变。

### 运行层级

1. `x5crop.cli`
   - 只负责解析命令行参数、打印启动摘要和处理终端进度。
   - 实际处理交给 `x5crop.workflow`。

2. `x5crop.workflow`
   - 负责 read -> deskew -> detect -> postprocess -> export -> report/debug 的批处理编排。
   - 不直接实现检测评分、candidate 选择或 TIFF 写入策略。

3. `x5crop.policies`
   - 通过 `get_detection_policy(format_id, strip_mode)` 解析一个 format / mode 的 `DetectionPolicy`。
   - `registry.py` 只做 policy resolve / cache。
   - `format_*.py` 拥有具体 format / mode policy preset。
   - `parameters.py` 是薄 lookup / public export。
   - `policies/presets/` 存放具体 format 参数。

4. `x5crop.detection`
   - 负责 outer proposal、separator/content evidence、candidate build/run、calibration、gates、selection 和 fallback。
   - `pipeline.py` 应保持 orchestration，不承载大块 format-specific 实现。
   - 重点模块包括 `candidate_build.py`、`candidate_run.py`、`calibration.py`、`fallback.py`、`outer.py`、`content.py`、`separator.py`、`scoring.py`、`gates.py`、`selection.py`、`partial_holder.py`、`dual_lane.py` 和 `outer_retry.py`。

5. `x5crop.geometry`、`x5crop.image`、`x5crop.io`
   - 提供低层 geometry、灰度/证据图和 TIFF I/O helper。
   - 需要 format 上下文的 helper 应显式接收 format/policy 参数，不应默认假设 135。
   - 这些层不应 import detection pipeline。

6. `x5crop.reports`、`x5crop.debug`、`x5crop.regression`
   - 消费稳定的 `Detection`、`ProcessResult` 和 report schema 数据。
   - 不应伸手进入 candidate generation 内部。

### Policy 归属

`DetectionPolicy` 是 runtime 行为入口。它应拥有或连接以下能力：

- `DetectorPolicy`：detector kind、135-dual lane metadata、unsupported partial reason。
- `CountPolicy`：full / partial count planning 和 partial offset。
- `OuterPolicy`：base outer、content-floating outer、edge-anchor outer、separator-first / separator-geometry outer、dark-band outer、outer retry。
- `SeparatorPolicy`：separator gate、gap search、edge-pair refinement、wide retry、enhanced separator、hard-gap trust、nearby correction、geometry support。
- `ContentPolicy`：content evidence、content profile、content mask、content candidate、content-support scoring。
- `ScoringPolicy`：base detection score、candidate calibration、content/geometry/separator support score、no-auto caps。
- `CandidateRunPolicy`：content candidate skip、separator-geometry competition、equal-first wide retry、dark-band retry、partial stop。
- `PartialHolderPolicy`：partial safe extra frames 和 strict holder safety。
- `SelectionPolicy`：candidate competition 和 content mismatch review fallback。
- `PostprocessPolicy`：final confidence caps、postprocess reason ids、approved geometry adjustment。
- `DiagnosticsPolicy`：Debug Analysis panels、gap overlay、nearby separator diagnostics、overlap-risk diagnostics。
- `ReportPolicy`：report schema version 和 report section order。
- `OutputPolicy`：detection bleed、output bleed、edge bleed protection。

### 必须隔离的 format / mode 行为

- `135` full 的稳定完整片条假设不能被其它 format 偷用。
- `135-dual` full 走 dual-lane detector；`135-dual` partial 仍是 review-only。
- half geometry support 是通用 capability，但默认只给 `half_full` 开启。
- `120-66` dark-band outer、wide-like separator、square-frame 和 strict holder checks 只给 `120-66` full / partial。
- `120-66` full 的 dark-band candidate selection 必须由 policy 控制，不能变成通用 full-strip 行为。
- `120-67` 可以保留自己的 short-axis / wide separator retry，但不能继承 `120-66` dark-band。
- `120-645` 共享 120 family 的保守 policy，但不启用 `120-66` dark-band。

### Candidate 和 report 契约

- `OuterCandidate.strategy` 是 candidate kind 契约。runtime 不应靠 name prefix 推断 dark-band、separator-first、edge-anchor 或 retry 行为。
- report detail 中的 `policy_id` 用于说明实际选择了哪套 policy。
- `report_schema` 应由 `ReportPolicy` 控制 schema version 和 section order。
- V4.5.4 golden reports 没有 `detail.policy` 和 `report_schema`，因此 metadata diff 应单独解释，不能和 crop behavior diff 混在一起。

### 验证要求

结构或 policy 改动后，至少跑：

```bash
python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py x5crop/policies/*.py x5crop/geometry/*.py x5crop/io/*.py x5crop/image/*.py x5crop/export/*.py x5crop/diagnostics/*.py x5crop/regression/*.py
git diff --check
python3 X5_Crop.py --version
```

policy smoke 应覆盖 14 个 format / mode：

```text
135 full / partial
135-dual full / partial
half full / partial
xpan full / partial
120-645 full / partial
120-66 full / partial
120-67 full / partial
```

核心 golden regression 字段：

```text
status
confidence
review_reasons
outer_box
frame_boxes
gaps
```

常用 V4.5.4 golden sets：

- `Test/135/4.5.4/split_report.jsonl`
- `Test/new_135/4.5.4/split_report.jsonl`
- `Test/120/66/4.5.4/split_report.jsonl`
- `Test/120/66/4.5.4_partial/split_report.jsonl`
- `Test/120/67/4.5.4/split_report.jsonl`
- `Test/半格/full/4.5.4/split_report.jsonl`
- `Test/半格/partial/4.5.4_partial/split_report.jsonl`

### 后续清理方向

- 继续把剩余 detector / geometry 参数从 flat preset 迁入 capability-specific policy。
- 保持 `pipeline.py` 只做 orchestration，把 candidate 细节留在专门模块。
- 删除或缩小旧兼容入口和隐式 fallback。
- 继续清理非目标 package wrapper 里的 `import *`。
- 每次迁移只推广接口，不推广默认行为。

## English Guide

### Document Role

- `README.md` and `快速启动_Quick_Start.md` are for regular users and Release use.
- `CHANGELOG.md` records version changes, validation results, and rollback context.
- `AGENTS.md` keeps Codex collaboration rules, the current handoff, and regression priorities.
- `ARCHITECTURE.md` is for continued development. It records source layers, policy ownership, and migration direction.

### Current Goal

V4.7 is a clean-room source rewrite. It is not meant to tune detector thresholds
or change crop output. Its purpose is to keep the V4.5.4 golden behavior while
making the active source work only through real responsibility modules.

Core principles:

- Treat the V4.5.4 `Test/` reports as the behavior baseline.
- Refactors should target 0 diff on core behavior fields before behavior changes are considered.
- Policy surfaces may become generic, but default activation must remain format-local.
- The `120-66` dark-band / square-frame risk model must remain isolated.
- Weak `grid`, `equal`, or content-only evidence must not gain auto-pass authority through structural cleanup.
- TIFF metadata, bit depth, ICC / resolution, and compression behavior are part of the public contract.

### Runtime Layers

1. `x5crop.cli`
   - Parses command-line arguments, prints the startup summary, and handles terminal progress.
   - Delegates actual processing to `x5crop.workflow`.

2. `x5crop.workflow`
   - Owns read -> deskew -> detect -> postprocess -> export -> report/debug orchestration.
   - Does not implement detector scoring, candidate selection, or TIFF write policy.

3. `x5crop.policies`
   - Resolves one `DetectionPolicy` for each format / mode through `get_detection_policy(format_id, strip_mode)`.
   - `registry.py` only resolves and caches policies.
   - Each `format_*.py` module owns its concrete format / mode policy preset.
   - `parameters.py` is a thin lookup / public export.
   - `policies/presets/` contains concrete format parameters.

4. `x5crop.detection`
   - Owns outer proposals, separator/content evidence, candidate build/run, calibration, gates, selection, and fallback.
   - `pipeline.py` should stay orchestration-only and should not carry large format-specific implementations.
   - Key modules include `candidate_build.py`, `candidate_run.py`, `calibration.py`, `fallback.py`, `outer.py`, `content.py`, `separator.py`, `scoring.py`, `gates.py`, `selection.py`, `partial_holder.py`, `dual_lane.py`, and `outer_retry.py`.

5. `x5crop.geometry`, `x5crop.image`, `x5crop.io`
   - Provide lower-level geometry, evidence image, and TIFF I/O helpers.
   - Helpers that need format context should receive explicit format/policy parameters and should not assume 135 by default.
   - These layers should not import the detection pipeline.

6. `x5crop.reports`, `x5crop.debug`, `x5crop.regression`
   - Consume stable `Detection`, `ProcessResult`, and report-schema data.
   - They should not reach into candidate generation internals.

### Policy Ownership

`DetectionPolicy` is the runtime behavior entry point. It should own or connect these capabilities:

- `DetectorPolicy`: detector kind, 135-dual lane metadata, unsupported partial reason.
- `CountPolicy`: full / partial count planning and partial offsets.
- `OuterPolicy`: base outer, content-floating outer, edge-anchor outer, separator-first / separator-geometry outer, dark-band outer, outer retry.
- `SeparatorPolicy`: separator gate, gap search, edge-pair refinement, wide retry, enhanced separator, hard-gap trust, nearby correction, geometry support.
- `ContentPolicy`: content evidence, content profile, content mask, content candidate, content-support scoring.
- `ScoringPolicy`: base detection score, candidate calibration, content/geometry/separator support score, no-auto caps.
- `CandidateRunPolicy`: content-candidate skip, separator-geometry competition, equal-first wide retry, dark-band retry, partial stop.
- `PartialHolderPolicy`: partial safe extra frames and strict holder safety.
- `SelectionPolicy`: candidate competition and content mismatch review fallback.
- `PostprocessPolicy`: final confidence caps, postprocess reason ids, approved geometry adjustment.
- `DiagnosticsPolicy`: Debug Analysis panels, gap overlay, nearby separator diagnostics, overlap-risk diagnostics.
- `ReportPolicy`: report schema version and report section order.
- `OutputPolicy`: detection bleed, output bleed, edge bleed protection.

### Format / Mode Behavior That Must Stay Isolated

- The stable full-strip assumption for `135` full must not leak into other formats.
- `135-dual` full uses the dual-lane detector; `135-dual` partial remains review-only.
- Half-frame geometry support is a generic capability, but it is enabled by default only for `half_full`.
- `120-66` dark-band outer, wide-like separator, square-frame, and strict holder checks are only for `120-66` full / partial.
- `120-66` full dark-band candidate selection must be policy-controlled and must not become generic full-strip behavior.
- `120-67` may keep its own short-axis / wide separator retry, but it must not inherit `120-66` dark-band behavior.
- `120-645` shares conservative 120-family policy, but does not enable `120-66` dark-band.

### Candidate And Report Contracts

- `OuterCandidate.strategy` is the candidate-kind contract. Runtime code should not infer dark-band, separator-first, edge-anchor, or retry behavior from name prefixes.
- `policy_id` in report detail explains which policy was actually selected.
- `report_schema` should use `ReportPolicy` for schema version and section order.
- V4.5.4 golden reports do not have `detail.policy` or `report_schema`, so metadata diffs should be explained separately from crop behavior diffs.

### Verification

After structural or policy changes, at minimum run:

```bash
python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py x5crop/policies/*.py x5crop/geometry/*.py x5crop/io/*.py x5crop/image/*.py x5crop/export/*.py x5crop/diagnostics/*.py x5crop/regression/*.py
git diff --check
python3 X5_Crop.py --version
```

Policy smoke should cover all 14 format / mode combinations:

```text
135 full / partial
135-dual full / partial
half full / partial
xpan full / partial
120-645 full / partial
120-66 full / partial
120-67 full / partial
```

Core golden regression fields:

```text
status
confidence
review_reasons
outer_box
frame_boxes
gaps
```

Common V4.5.4 golden sets:

- `Test/135/4.5.4/split_report.jsonl`
- `Test/new_135/4.5.4/split_report.jsonl`
- `Test/120/66/4.5.4/split_report.jsonl`
- `Test/120/66/4.5.4_partial/split_report.jsonl`
- `Test/120/67/4.5.4/split_report.jsonl`
- `Test/半格/full/4.5.4/split_report.jsonl`
- `Test/半格/partial/4.5.4_partial/split_report.jsonl`

### Follow-Up Cleanup

- Keep moving remaining detector / geometry parameters from flat presets into capability-specific policy.
- Keep `pipeline.py` orchestration-only and leave candidate details in focused modules.
- Remove or narrow legacy compatibility entries and implicit fallback paths.
- Continue cleaning `import *` from non-target package wrappers.
- Migrate interfaces without broadening default behavior.
