# X5 Crop 架构说明 / Architecture Guide

本文件是开发者架构地图，范围限定为源码分层、policy 行为边界、format / mode
隔离规则和验证要求。使用说明见 `README.md`，版本摘要见 `CHANGELOG.md`，
Codex 协作规则见 `AGENTS.md`。

This file is the developer architecture map. It covers source layers, policy
ownership, format / mode isolation, and verification requirements. For usage,
read `README.md`; for version history, read `CHANGELOG.md`; for Codex rules,
read `AGENTS.md`.

## 中文说明

### 架构目标

V4.9 是 evidence-governed policy reset。目标不是提高自动通过数量，而是让自动裁切
只发生在 outer、separator、geometry、content 和 risk 证据能够共同解释时。

架构原则：

- 入口精简，运行配置明确。
- workflow 只承担单图和批处理编排。
- format physical facts 与 policy decision rules 分离。
- detection 生成证据、候选和最终 PASS / REVIEW。
- geometry / image / io 提供底层能力，不拥有候选或决策语义。
- report / debug / export 只消费稳定结果，不反向参与候选选择。
- developer tools 位于 `tools/`，不进入 runtime package。

### 分层边界

| 层级 | 主要职责 |
|---|---|
| `X5_Crop.py` | 开发入口；Release 构建生成单文件发布版。 |
| `x5crop.cli` / `cli_options` / `runtime_config` | CLI 解析、入口参数契约、运行配置契约。 |
| `x5crop.interactive` / launchers | 交互式菜单；平台启动器只负责找到 Python 并进入交互模式。 |
| `x5crop.input_probe` / `x5crop.app` | 输入 TIFF 探测、layout 解析、启动摘要、worker 调度。 |
| `x5crop.workflow` | read -> deskew -> detect -> finalization -> export -> report/debug 编排。 |
| `x5crop.formats` | format identity、physical spec、count/aspect facts 和 CLI choices 的唯一入口。 |
| `x5crop.policies` | runtime policy、decision contract、format / mode presets、参数解析和 policy detail 序列化。 |
| `x5crop.geometry` / `image` / `io` | box、gap、separator profile、deskew、pixel transform、TIFF I/O 等底层能力。 |
| `x5crop.detection` | outer proposals、evidence、candidate lifecycle、candidate assessment、finalization 和 PASS / REVIEW。 |
| `analysis_reuse` / `export` / `result_builder` / `report_schema` / `report_outputs` / `debug` | 缓存复用、TIFF 输出、结果组装、报告 schema、报告写入和 Debug Analysis。 |
| `tools` | standalone build、reference compare、safety classification 等开发工具。 |

依赖方向应从入口和工作流流向基础层；基础层不得反向依赖 workflow、detection、
debug、report 或 policy registry。

### 命名和 API 规则

- `*Options`: 文件探测前的入口参数，例如 `CliOptions`。
- `*Config`: 已解析运行配置，例如 `RuntimeConfig`。
- `*Spec`: 物理事实或格式规格，例如 `FormatSpec`。
- `*Parameters`: 数值参数和低层执行参数。
- `*Policy`: format / mode 行为、gate、decision 或 output 规则。
- `*Assessment`: candidate 阶段评估结果；不得表达最终裁切决定。
- `*Decision*`: 最终 PASS / REVIEW 语义。
- `*Result`: 已完成流程的返回对象。

当前 module、class、function、policy id 和架构标签应使用语义命名。版本号只应出现在
`VERSION` / `APP_VERSION`、release history、artifact 名、historical archive path
和 machine schema value 中。

### Policy 和决策模型

`DetectionDecisionContract` 是 public decision policy contract，包含：

- `ModePolicy`: full / partial count、outer、stop condition、edge trust。
- `EvidencePolicy`: outer / separator / geometry / content 的最低组合证据。
- `RiskPolicy`: overlap、outer-content mismatch、candidate competition、partial edge uncertainty 等 REVIEW 风险。
- `CandidatePolicy`: content-only、fallback、weak-grid、equal-gap 候选的默认保守行为。
- `DecisionPolicy`: PASS / REVIEW reason id 和 confidence cap。
- `OutputPolicy`: TIFF metadata/export 行为和输出 bleed。
- `DecisionDiagnosticsPolicy`: decision/report 中记录的 diagnostics 和 overlay 说明。

runtime `DetectionPolicy` 仍用于 evidence generation wiring。它连接 detector、count、
outer、separator、content、scoring、candidate run、selection、finalization、
diagnostics、report 和 output 等 runtime 能力。影响最终 PASS / REVIEW 的参数必须进入
report schema 的 decision policy detail。

### 必须隔离的行为

- 135 full 的完整片条假设不能推广给其它 format。
- 135-dual full 使用 dual-lane detector；135-dual partial 保守复核。
- half geometry support 是通用 capability，但默认只给 `half/full` 开启。
- 120-66 dark-band、square-frame、wide-like separator 和 strict-holder checks
  只适用于 120-66 full / partial。
- 120-67 可以有自己的 short-axis / wide-separator retry，但不能继承 120-66 dark-band。
- weak grid、equal、content-only、fallback 或不可信 partial-edge 证据不能获得自动 PASS 权限。

### 数据和报告契约

- `CliOptions` 是文件探测前的用户选项；`RuntimeConfig` 是绑定输入和 layout 后的运行配置。
- `OuterCandidate.strategy` 是 candidate kind 契约；runtime 不应靠 name prefix 推断行为。
- `Detection` 和 `ProcessResult` 是 report、debug 和 export 的稳定输入。
- report row 顶层包含 `version` 和 `policy_id`。
- V4.9 使用 `v4_9_policy_schema_1`，包含 evidence、risk、decision policy 和 selected candidate detail。
- V4.5.4 / V4.7 reports 是 historical reference，不再是必须 0 diff 的 oracle。
  新增错误 PASS 不可接受；保守 REVIEW 和 schema/reason diff 必须解释。

### 验证要求

结构或 policy 改动后至少运行：

```bash
python3 -m compileall -q X5_Crop.py x5crop
bash -n X5_Crop_Mac.command
bash -n X5_Crop_Mac_diagnostics.command
git diff --check
python3 X5_Crop.py --version
```

如果 checkout 展开了 `tools/`，同时编译 `tools/regression/*.py`。Release build 工具
改动还应运行 `tools/build_standalone.py`，并对生成的单文件执行 `--version` smoke。

检测行为改动使用 reference classifier：

```bash
python3 -m tools.regression.reference_classify --candidate-root <root>
```

核心字段：

```text
status
confidence
review_reasons
outer_box
frame_boxes
gaps
```

常用 reference sets：

```text
Test/135/4.5.4/split_report.jsonl
Test/new_135/4.5.4/split_report.jsonl
Test/120/66/4.5.4/split_report.jsonl
Test/120/66/4.5.4_partial/split_report.jsonl
Test/120/67/4.5.4/split_report.jsonl
Test/半格/full/4.5.4/split_report.jsonl
Test/半格/partial/4.5.4_partial/split_report.jsonl
```

验收重点是 0 `unacceptable_wrong_pass` 和 0 无解释的 `risky_regression`。

## English Guide

### Architecture Goal

V4.9 is an evidence-governed policy reset. Its goal is not to increase automatic
PASS count, but to export crops automatically only when outer, separator,
geometry, content, and risk evidence jointly explain the decision.

Principles:

- Keep entry points thin and runtime configuration explicit.
- Keep workflow as orchestration only.
- Separate format physical facts from policy decision rules.
- Let detection own evidence, candidates, and final PASS / REVIEW.
- Keep geometry / image / io as lower-level capabilities without candidate or decision semantics.
- Let report / debug / export consume stable results only.
- Keep developer tools under `tools/`, outside the runtime package.

### Layer Boundaries

| Layer | Responsibility |
|---|---|
| `X5_Crop.py` | Development entry; Release builds produce the standalone script. |
| `x5crop.cli` / `cli_options` / `runtime_config` | CLI parsing, entry option contract, runtime configuration contract. |
| `x5crop.interactive` / launchers | Interactive menu; platform launchers only locate Python and enter interactive mode. |
| `x5crop.input_probe` / `x5crop.app` | TIFF input probing, layout resolution, startup summary, worker dispatch. |
| `x5crop.workflow` | read -> deskew -> detect -> finalization -> export -> report/debug orchestration. |
| `x5crop.formats` | Single source of truth for format identity, physical specs, counts/aspects, and CLI choices. |
| `x5crop.policies` | Runtime policy, decision contract, format/mode presets, parameter resolution, policy detail serialization. |
| `x5crop.geometry` / `image` / `io` | Boxes, gaps, separator profiles, deskew, pixel transforms, TIFF I/O, and other lower-level capabilities. |
| `x5crop.detection` | Outer proposals, evidence, candidate lifecycle, candidate assessment, finalization, PASS / REVIEW. |
| `analysis_reuse` / `export` / `result_builder` / `report_schema` / `report_outputs` / `debug` | Cache reuse, TIFF output, result assembly, report schema, report writing, Debug Analysis. |
| `tools` | Standalone build, reference compare, safety classification, and other developer tools. |

Dependencies should flow from entry/workflow toward foundation layers. Foundation
layers must not depend back on workflow, detection, debug, report, or the policy
registry.

### Naming And API Rules

- `*Options`: entry options before file probing.
- `*Config`: resolved runtime configuration.
- `*Spec`: physical facts or format specifications.
- `*Parameters`: numeric or low-level execution parameters.
- `*Policy`: format / mode behavior, gates, decisions, or output rules.
- `*Assessment`: candidate-stage evaluation.
- `*Decision*`: final PASS / REVIEW semantics.
- `*Result`: completed process return objects.

Current module, class, function, policy id, and architecture names should be
semantic. Version tags belong only in version constants, release history,
artifact names, archive paths, and machine schema values.

### Policy And Decision Model

`DetectionDecisionContract` is the public decision policy contract:

- `ModePolicy`: full / partial count, outer, stop condition, edge trust.
- `EvidencePolicy`: minimum combined outer / separator / geometry / content evidence.
- `RiskPolicy`: review risks such as overlap, outer-content mismatch, competition, partial-edge uncertainty.
- `CandidatePolicy`: conservative defaults for content-only, fallback, weak-grid, and equal-gap candidates.
- `DecisionPolicy`: PASS / REVIEW reason ids and confidence caps.
- `OutputPolicy`: TIFF metadata/export behavior and output bleed.
- `DecisionDiagnosticsPolicy`: diagnostics and overlay details recorded in decision/report.

Runtime `DetectionPolicy` remains the evidence-generation wiring surface. Any
parameter that affects final PASS / REVIEW must be present in report schema
decision policy detail.

### Behavior That Must Stay Isolated

- 135 full-strip assumptions must not leak into other formats.
- 135-dual full uses the dual-lane detector; 135-dual partial stays conservative.
- Half-frame geometry support is generic, but currently enabled only for
  `half/full`.
- 120-66 dark-band, square-frame, wide-like separator, and strict-holder checks
  stay limited to 120-66 full / partial.
- 120-67 may have its own retry behavior, but must not inherit 120-66 dark-band behavior.
- Weak grid, equal, content-only, fallback, or untrusted partial-edge evidence
  must not gain automatic PASS authority.

### Data And Report Contracts

- `CliOptions` records user options before file probing; `RuntimeConfig` records
  resolved input/layout runtime configuration.
- `OuterCandidate.strategy` is the candidate-kind contract.
- `Detection` and `ProcessResult` are stable report/debug/export inputs.
- Report rows include top-level `version` and `policy_id`.
- V4.9 uses `v4_9_policy_schema_1` with evidence, risk, decision policy, and selected candidate detail.
- V4.5.4 / V4.7 reports are historical references, not mandatory 0-diff oracles.
  New wrong PASS is unacceptable; conservative REVIEW and schema/reason diffs
  require explanation.

### Verification

After structure or policy changes, run:

```bash
python3 -m compileall -q X5_Crop.py x5crop
bash -n X5_Crop_Mac.command
bash -n X5_Crop_Mac_diagnostics.command
git diff --check
python3 X5_Crop.py --version
```

If `tools/` is expanded, also compile `tools/regression/*.py`. For detector
behavior changes, classify reference reports with:

```bash
python3 -m tools.regression.reference_classify --candidate-root <root>
```

The acceptance target is 0 `unacceptable_wrong_pass` and 0 unexplained
`risky_regression`.
