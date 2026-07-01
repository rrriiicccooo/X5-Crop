# X5 Crop 架构说明 / Architecture Guide

本文件是开发者架构地图，范围限定为源码分层、policy 行为边界、
format / mode 隔离规则，以及行为保持型重构的验证要求。

This document is the developer architecture map. It describes source layers,
policy ownership, format / mode isolation, and behavior-preserving verification.

使用说明请参阅 `README.md`。版本历史请参阅 `CHANGELOG.md`。
Codex 协作规则请参阅 `AGENTS.md`。

For usage, read `README.md`. For version history, read `CHANGELOG.md`. For Codex
collaboration rules, read `AGENTS.md`.

## 中文说明

### 架构目标

V4.7 是一次 clean-room source rewrite。目标不是调检测阈值，也不是改变裁切结果，
而是在保持 V4.5.4 golden 输出行为的前提下，让 active source 按真实职责组织：

- 入口保持精简。
- workflow 只承担编排职责。
- detection 只承担检测和候选决策职责。
- geometry / image / io 提供低层能力。
- policy 拥有 format / mode 行为开关。
- report / debug / regression 消费稳定结果，不反向驱动检测。

### 运行层级

1. `X5_Crop.py`
   - 开发入口。
   - V4 Release 会由构建脚本生成单文件发布版。

2. `x5crop.cli`
   - 解析命令行参数。
   - 打印启动摘要和终端进度。
   - 不实现检测逻辑。

3. `x5crop.workflow`
   - 编排 read -> deskew -> detect -> postprocess -> export -> report/debug。
   - 处理批量任务、报告复用、输出目录和 worker 调度。
   - 不直接实现 scoring、candidate selection 或 TIFF 写入细节。

4. `x5crop.policies`
   - 通过 `get_detection_policy(format_id, strip_mode)` 解析 runtime policy。
   - `registry.py` 只做 resolve/cache。
   - `format_*.py` 拥有各 format / mode 的 policy preset。
   - `presets/` 保存 format 参数；`parameters.py` 是薄 lookup / public export。

5. `x5crop.detection`
   - 负责 outer proposal、separator/content evidence、candidate build/run、
     scoring、gates、selection、fallback 和 postprocess。
   - `pipeline.py` 应保持主流程 orchestration。
   - 专门模块承接具体职责，例如 `candidate_build.py`、`candidate_run.py`、
     `dual_lane.py`、`partial_holder.py`、`outer_retry.py`、`calibration.py`、
     `gates.py`、`selection.py` 和 `postprocess.py`。

6. `x5crop.geometry` / `x5crop.image` / `x5crop.io`
   - 提供 box、layout、gap、separator profile、frame fit、output adjustment、
     deskew、证据图和 TIFF I/O helper。
   - 需要 format 上下文的 helper 应显式接收 format 或 policy。
   - 这些层不应依赖 detection pipeline。

7. `x5crop.reports` / `x5crop.debug` / `x5crop.regression`
   - 消费稳定的 `Detection`、`ProcessResult` 和 report schema。
   - 不参与候选生成和 PASS/REVIEW 决策。

### Policy 归属

`DetectionPolicy` 是 runtime 行为入口。它应拥有或连接这些能力：

- `DetectorPolicy`: detector kind、135-dual lane metadata、unsupported partial reason。
- `CountPolicy`: full / partial count planning 和 partial offsets。
- `OuterPolicy`: base outer、separator-derived outer、dark-band outer、outer retry。
- `SeparatorPolicy`: gate、gap search、edge-pair、wide retry、profile、enhanced separator、hard-gap trust、nearby correction、geometry support。
- `ContentPolicy`: content evidence、profile、mask、content candidate、content-support scoring。
- `ScoringPolicy`: base detection score、candidate calibration、content/geometry/separator support score、no-auto caps。
- `CandidateRunPolicy`: content candidate skip、separator-geometry competition、equal-first wide retry、dark-band retry、partial stop。
- `PartialHolderPolicy`: partial safe-extra-frames 和 strict holder safety。
- `SelectionPolicy`: candidate competition 和 content mismatch review fallback。
- `PostprocessPolicy`: final caps、postprocess reason ids、approved geometry adjustment。
- `DiagnosticsPolicy`: Debug Analysis panels、gap overlay、nearby separator diagnostics、overlap-risk diagnostics。
- `ReportPolicy`: report schema version 和 section order。
- `OutputPolicy`: detection bleed、output bleed、edge bleed protection。

新增 capability 可以做成通用接口，但默认启用范围必须由具体 format / mode policy 决定。

### 必须隔离的行为

- 135 full 的稳定完整片条假设不能被其它 format 偷用。
- 135-dual full 走 dual-lane detector；135-dual partial 保守复核。
- half geometry support 是通用 capability，但默认只给 `half_full` 开启。
- 120-66 dark-band、square-frame、wide-like separator 和 strict holder checks
  只给 120-66 full / partial。
- 120-67 可以有自己的 short-axis / wide separator retry，但不能继承 120-66 dark-band。
- weak grid、equal 或 content-only evidence 不能因为重构获得自动 PASS 权限。

### 数据和报告契约

- `OuterCandidate.strategy` 是 candidate kind 契约。runtime 不应靠 name prefix 推断行为。
- `Detection` 和 `ProcessResult` 是 report/debug/export 的稳定输入。
- report detail 中的 policy id 用于说明实际选择了哪套 policy。
- `report_schema` 由 `ReportPolicy` 控制 schema version 和 section order。
- V4.5.4 golden reports 没有 V4.7 的 `detail.policy` 和 `report_schema`，
  metadata diff 必须和 crop behavior diff 分开解释。

### 验证边界

结构或 policy 改动后至少运行：

```bash
python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py x5crop/policies/*.py x5crop/geometry/*.py x5crop/io/*.py x5crop/image/*.py x5crop/export/*.py x5crop/diagnostics/*.py x5crop/regression/*.py
git diff --check
python3 X5_Crop.py --version
```

检测行为改动需要比较核心字段：

```text
status
confidence
review_reasons
outer_box
frame_boxes
gaps
```

常用 golden sets：

```text
Test/135/4.5.4/split_report.jsonl
Test/new_135/4.5.4/split_report.jsonl
Test/120/66/4.5.4/split_report.jsonl
Test/120/66/4.5.4_partial/split_report.jsonl
Test/120/67/4.5.4/split_report.jsonl
Test/半格/full/4.5.4/split_report.jsonl
Test/半格/partial/4.5.4_partial/split_report.jsonl
```

验收默认目标是 0 core diff。若出现 diff，必须逐条说明为什么更正确、更保守或更稳定。

## English Guide

### Architecture Goal

V4.7 is a clean-room source rewrite. It is not meant to tune detector thresholds
or change crop output. Its purpose is to preserve V4.5.4 golden behavior while
keeping active source organized by real responsibilities:

- Thin entry.
- Workflow only orchestrates.
- Detection owns evidence and candidate decisions.
- Geometry / image / io provide lower-level capabilities.
- Policy owns format / mode behavior switches.
- Report / debug / regression consume stable results and do not drive detection.

### Runtime Layers

1. `X5_Crop.py`
   - Development entry.
   - V4 Release builds produce a standalone single-file script.

2. `x5crop.cli`
   - Parses CLI arguments.
   - Prints startup summary and terminal progress.
   - Does not implement detector logic.

3. `x5crop.workflow`
   - Orchestrates read -> deskew -> detect -> postprocess -> export -> report/debug.
   - Owns batch processing, report reuse, output folders, and worker scheduling.

4. `x5crop.policies`
   - Resolves runtime policy through `get_detection_policy(format_id, strip_mode)`.
   - `registry.py` only resolves and caches.
   - `format_*.py` modules own concrete format / mode policy presets.
   - `presets/` stores format parameters; `parameters.py` is a thin lookup/export layer.

5. `x5crop.detection`
   - Owns outer proposals, separator/content evidence, candidate build/run,
     scoring, gates, selection, fallback, and postprocess.
   - `pipeline.py` should stay orchestration-focused.

6. `x5crop.geometry` / `x5crop.image` / `x5crop.io`
   - Provide boxes, layout, gaps, separator profiles, frame fit, output
     adjustment, deskew, evidence images, and TIFF I/O.
   - Helpers that need format context should receive format or policy explicitly.
   - These layers should not depend on the detection pipeline.

7. `x5crop.reports` / `x5crop.debug` / `x5crop.regression`
   - Consume stable `Detection`, `ProcessResult`, and report schema data.
   - Do not generate candidates or decide PASS/REVIEW.

### Policy Ownership

`DetectionPolicy` is the runtime behavior entry. It owns or connects detector,
count, outer, separator, content, scoring, candidate-run, partial-holder,
selection, postprocess, diagnostics, report, and output policy surfaces.

General capability interfaces are welcome, but activation must remain scoped by
concrete format / mode presets.

### Behavior That Must Stay Isolated

- 135 full-strip assumptions must not leak into other formats.
- 135-dual full uses the dual-lane detector; 135-dual partial stays conservative.
- Half-frame geometry support is generic, but currently enabled only for
  `half_full`.
- 120-66 dark-band, square-frame, wide-like separator, and strict-holder checks
  stay limited to 120-66 full / partial.
- 120-67 may have its own short-axis / wide-separator retry, but must not inherit
  120-66 dark-band behavior.
- Weak grid, equal, or content-only evidence must not gain auto-PASS authority
  through refactoring.

### Data And Report Contracts

- `OuterCandidate.strategy` is the candidate-kind contract. Runtime should not
  infer behavior from name prefixes.
- `Detection` and `ProcessResult` are stable inputs for report/debug/export.
- Report detail records the selected policy id.
- `ReportPolicy` owns `report_schema` version and section order.
- V4.5.4 golden reports lack V4.7 `detail.policy` and `report_schema`, so
  metadata diffs must be explained separately from crop behavior diffs.

### Verification

After structure or policy changes, run:

```bash
python3 -m py_compile X5_Crop.py x5crop/*.py x5crop/detection/*.py x5crop/debug/*.py x5crop/policies/*.py x5crop/geometry/*.py x5crop/io/*.py x5crop/image/*.py x5crop/export/*.py x5crop/diagnostics/*.py x5crop/regression/*.py
git diff --check
python3 X5_Crop.py --version
```

For detector behavior changes, protect:

```text
status
confidence
review_reasons
outer_box
frame_boxes
gaps
```

The default acceptance target is 0 core diff. Any diff must be explained as more
correct, more conservative, or more stable.
