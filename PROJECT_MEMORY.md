# Project Memory / 项目记忆

Updated / 更新：2026-07-25

This is the sole cross-session checkpoint for X5 Crop. It is a concise map, not
an instruction source or completion proof. Current user intent, Git, source,
original TIFFs, current reports, Debug Analysis, and live command output remain
authoritative.

本文件是 X5 Crop 唯一跨会话检查点，只保存当前地图，不是指令或完成证明。当前用户目标、
Git、源码、原始 TIFF、current report、Debug Analysis 与现场命令始终优先。

## Current Objective / 当前目标

Build a new no-bleed golden baseline from zero through local machine-assisted
human review. Complete long TIFFs stay outside model vision: local numerical
tools may create an editable seed, but only the user may copy, inspect, adjust,
assess all four boundaries, and explicitly confirm a baseline row.

从零建立新的无 bleed 黄金基线。完整长 TIFF 不进入模型视觉；本地数值工具可以生成可编辑
seed，但只有用户逐边检查、拖动修正、填写四边判断并明确确认后，才能产生 baseline。

- Do not send complete long TIFFs to model vision for coordinate authorship. /
  不再让模型通过完整长 TIFF 生成 reference 坐标。
- Do not restore, reconstruct, import, or migrate deleted assistant proposals
  or retired reference files. / 不恢复、不重建、不导入、不迁移已删除的模型草稿或旧
  reference 文件。
- Do not promote X5 Crop, a machine seed, confidence, low residual, generated
  JPGs, hashes, or algorithm agreement into ground truth. / 项目输出、机器候选、
  confidence、低残差、生成物与算法一致均不是 ground truth。
- Only source-SHA-bound coordinates explicitly reviewed and confirmed by the
  user, or an independently calibrated external measurement, may enter the
  baseline. Visually indeterminate geometry remains unresolved. / 只有绑定
  source SHA、经用户明确审阅和确认的原图坐标，或独立校准的外部测量，才能进入 baseline；
  看不清保持 unresolved。
- Detector calibration is paused until the new user-confirmed baseline has
  representative coverage. / 新一轮用户确认 baseline 达到代表性覆盖前，不继续用样片
  调 detector。

## Verified Checkpoint / 已核对检查点

- Branch / 分支：`main`.
- Reset base / 本次归零起点：`97abbbd5`
  (`Reset manual reference workspace`); always check live `HEAD` when resuming.
- Current report revision / 当前报告 revision：
  `cross_region_photo_edge_geometry`.
- The local source library contains 111 original TIFFs: 47 `135/full`,
  14 `135/partial`, 32 `120-66/partial`, 3 `120-67/full`,
  10 `half/full`, and 5 `half/partial`. `Test/` is untracked local evidence,
  not a source contract. / 当前本地样片为 111 张，`Test/` 不受 Git 跟踪。
- `Test/manual_review/manifest.jsonl` contains the current stable `S001–S111`
  source identities, full relative paths, SHA-256 values, raster dimensions,
  TIFF orientation metadata, and nine gold-cohort markers. / 当前 manifest 已绑定
  111 张原图身份与 9 张黄金集标记。
- `Test/manual_review/annotator/candidate_generator.py` independently reads the
  nine gold originals with tifffile/imagecodecs and uses NumPy, OpenCV, SciPy,
  and Pillow-side display support without importing the production detector,
  reports, Debug Analysis, or model vision. / 本地候选生成器与 production detector、
  report、Debug、模型视觉隔离。
- `Test/manual_review/machine_candidates.jsonl` contains nine
  `x5crop_machine_review_candidate_v1` records and 46 editable frame seeds.
  Numerical review gates passed: every safe polygon is a strict inset, adjacent
  polygons do not geometrically overlap, heuristic confidence is
  `0.698–0.949`, and maximum fit uncertainty is `6.79 px`. These are review
  diagnostics, not correctness probabilities. / 当前有 9 张、46 个可编辑机器 seed；
  数值门槛通过，但不是正确率证明。
- The browser annotator uses `x5crop_manual_review_proposal_v2` and
  `x5crop_human_confirmed_baseline_v2`. Machine seeds stay in a separate
  digest-protected channel; copying creates only an unsaved editable draft.
  A browser test copied S027 F1 and moved one point by one raw pixel, then
  reloaded without saving. / 标注器已实测候选复制与原图 1 px 修正，测试草稿已丢弃。
- Focused verification passed 27 annotator contracts, all 111 live source
  SHA-256 checks, candidate numerical verification, and JavaScript/Python syntax
  checks. Active state remains `0 proposals / 0 confirmed baseline rows`. /
  工具验证通过；活动 proposal 与确认 baseline 仍均为 0。
- `tools/verify full` passed 826 tests and 14 format/mode configuration checks
  after this synchronization. This is mechanical evidence only. / 本次同步后完整
  verifier 通过 826 项测试与 14 组配置；它只证明机械一致性。
- `Test/manual_review/findings.md` contains no current visual finding. /
  当前没有样片视觉结论。
- All previous assistant-authored proposals and review artifacts remain
  deleted. No retired proposal, baseline, archive, or review JPG is retained;
  only the new non-authoritative machine-candidate file exists. / 旧模型 proposal、
  baseline、archive 与审阅 JPG 仍全部删除；只新增了无权威机器候选。
- The tooling audit remains closed around `tools/verify`, `tools/git/`,
  `tools/release/`, `tools/regression/compare.py`, and `tools/tests/`. /
  tracked tools 的职责边界未改变。

## Selected Gold Cohort / 已选黄金集

These nine originals remain useful representatives, but selection is not a
label or confirmation:

下列 9 张仍可作为代表样片，但“入选”不等于已有标签或确认：

| Group / 类别 | Sources / 样片 |
|---|---|
| `135/full` | `pass_X5_00027.tif`, `pass_X5_00035.tif` |
| `135/partial` | `pass_X5_00004.tif`, `unknown_X5_00003.tif` |
| `66/partial` | `pass_X5_00001.tif`, `pass_X5_00030.tif` |
| `67/full` | `pass_X5_00001.tif` |
| `half/full` | `pass_X5_00002.tif` |
| `half/partial` | `pass_X5_00003.tif` |

Full identities live only in the current manifest; same basenames in different
groups are different sources. / 完整身份只以 current manifest 为准，不同目录的同名
文件不是同一身份。

## V5 Dependency Boundary / V5 依赖边界

The two previously reserved large V5 dependencies were OpenCV and SciPy. The
current local Python can import NumPy 2.5.1, tifffile 2026.7.14, imagecodecs
2026.6.26, Pillow 12.2.0, OpenCV 5.0.0, and SciPy 1.18.0. OpenCV and SciPy are
now used only by the ignored local candidate generator; X5 Crop V4.9 runtime
still does not depend on them.

此前为 V5 预留的两个大依赖是 OpenCV 与 SciPy。当前本机 Homebrew Python 可导入
完整数值栈；OpenCV 与 SciPy 目前只用于本地候选生成器，V4.9 runtime 没有引入它们。

- OpenCV can provide mature gradients, contours, line fitting, subpixel
  refinement, transforms, and local UI support. / OpenCV 可提供成熟边缘、轮廓、
  直线拟合、亚像素修正与变换。
- SciPy can provide filtering, interpolation, optimization, robust fitting, and
  statistical uncertainty calculations. / SciPy 可提供滤波、插值、优化、稳健拟合与
  不确定度计算。
- They can process full TIFFs locally without consuming model context and can
  improve candidate generation or measurement reproducibility. They cannot
  reveal an occluded or visually ambiguous physical edge, prove semantic edge
  identity, or create an absolute oracle. Agreement between them is still
  machine consensus over the same pixels. / 它们能避免模型上下文问题并提高候选与
  测量复现性，但不能看见被遮挡或不可辨的真实边缘，也不能形成绝对 oracle。

## Manual Review Reset / 人工审阅归零

There is no current manual crop, deskew, photo-edge, frame-slot, expectation, or
human-confirmed baseline. Active proposals and confirmed baseline rows are both
zero. The nine machine candidates are non-authoritative inputs only. The next
baseline row must be created afresh by copying or directly drawing current
geometry, reviewing it in native pixels, saving a proposal, and explicitly
confirming it.

当前没有任何有效人工或 human-confirmed baseline；活动 proposal 与确认 baseline 均为
0，也不再保留旧 reference 材料。九张机器候选只是无权威输入；下一条 baseline 必须由
用户在 current schema 中重新审阅并明确确认。

## Validation Boundary And Open Risks / 验证边界与开放风险

- The annotator contracts prove identity, coordinate transforms, write
  authority, file integrity, and bounded candidate geometry only. They do not
  prove that any boundary is physically correct. / 工具通过只证明合同、文件和候选
  数值范围一致，不证明边界正确。
- Gold frame counts are candidate-generation priors, not labels. Heuristic
  confidence and uncertainty rank review attention; they are not probabilities
  or truth. / 黄金集 Frame 数只是候选生成先验；confidence 与 uncertainty 只用于
  安排审阅优先级。
- Direct user clicking can establish a practical authoritative reference, but
  not mathematical certainty where the TIFF itself is ambiguous. Absolute
  physical truth requires an independent calibration surface or measurement. /
  用户点击可形成实用权威；若像素不可辨，绝对物理真值仍需外部独立校准。
- `Test/` is ignored, so a clean Git worktree does not mean the local review
  workspace is empty. / Git clean 不代表 `Test/manual_review/` 为空。
- Historical `/private/tmp/x5crop-*` diagnostic and safety directories were
  inventoried but left untouched; some are deliberate recovery copies. /
  `/private/tmp` 中的历史诊断与安全副本未删除。
- Mechanical verifier success never establishes named-TIFF geometry. /
  全量 verifier 通过不等于真实样片物理正确。

## Next Decision And Actions / 下一决策与行动

1. Open the local annotator, start with an easy sample such as S027 to learn the
   controls, then prioritize the weakest fits: S035 F2/F3/F5/F6 and S098 F7. /
   先用 S027 熟悉操作，再优先审阅 S035 F2/F3/F5/F6 与 S098 F7。
2. For every frame, copy the machine seed or draw directly, inspect all edges
   and corners in native pixels, drag or arrow-adjust points, assess all four
   boundaries, save the proposal, and explicitly confirm only when satisfied. /
   每个 Frame 都需逐边逐角检查、修点、填写四边判断、保存，再明确确认。
3. Leave ambiguous geometry `unresolved`; use an independent calibrated
   measurement if mathematical physical certainty is required. / 看不清保持
   `unresolved`；若要求数学物理绝对值，必须引入独立校准测量。
4. Confirm representative gold-cohort frames before expanding the pass. Do not
   reconstruct or import deleted reference material. / 先完成黄金样片，再扩展审阅。
5. Only after an independent baseline exists should detector calibration,
   fresh blind validation, performance profiling, and the 111-sample audit
   resume. / 先有独立基准，再继续 detector 校准、盲测、性能与全量审计。

## Exact Resume / 精确恢复

Run these read-only checks first:

```bash
git log -1 --oneline
git status --short
find Test -type f \( -iname '*.tif' -o -iname '*.tiff' \) | sort
wc -l Test/manual_review/manifest.jsonl
find Test/manual_review -maxdepth 4 -type f | sort
python3 -B -m unittest Test/manual_review/annotator/test_annotator.py
python3 -B Test/manual_review/annotator/candidate_generator.py verify
python3 -B Test/manual_review/annotator/server.py verify
python3 -B Test/manual_review/annotator/server.py serve
rg 'REPORT_SCHEMA_REVISION' x5crop
```

Resume prompt / 恢复提示：

> 从当前 111-source manifest、9 张非权威机器候选与 machine-assisted annotator
> 继续。活动 proposal 和 baseline 均应为 0。逐 Frame 复制候选或直接画点，在原生像素中
> 修正并填写四边判断，保存后由用户明确确认；看不清保持 unresolved，不恢复旧材料。
