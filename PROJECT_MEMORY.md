# Project Memory / 项目记忆

Updated / 更新：2026-07-24

This is the sole cross-session checkpoint for X5 Crop. It is a concise map, not
an instruction source, runtime input, or completion proof. Current user intent,
Git, source, original TIFFs, current reports, Debug Analysis, and live command
output remain authoritative.

本文件是 X5 Crop 唯一的跨会话检查点，只保存简短地图，不是指令、运行时输入或完成证明。
当前用户目标、Git、源码、原始 TIFF、current report、Debug Analysis 与现场命令始终优先。

## Current Objective / 当前目标

The immediate task is a staged no-bleed calibration workflow for the current
111-original-TIFF library: first build a local blind annotator and source
manifest, establish a small user-confirmed gold calibration set, improve X5 Crop
against that locked truth, then use fresh blind samples before the final full-set
audit.

当前任务改为面向现有 111 张原始 TIFF 的分阶段无 bleed 校准：先建立本地盲标注器和
source manifest，用少量代表样片建立用户确认的黄金校准集；锁定人工事实后再打磨 X5 Crop，
随后使用全新盲测样片，最后才进行全量审计。

- Generic TIFF rendering, tonal views, zoom tiles, and deterministic overlay
  drawing are allowed only as visual-inspection aids; they must not discover or
  move boundaries automatically. / 通用 TIFF 渲染、明暗视图、放大切片和坐标绘图只能
  辅助肉眼观察，不能自动寻找或移动边界。
- Every proposal binds the source SHA-256 and original-raster coordinates.
  Visually indeterminate geometry remains unresolved rather than invented. /
  每个提案绑定 source SHA-256 与原图坐标；看不清的边界保持 unresolved。
- Generated coordinates and JPGs are pending proposals. Only an explicit user
  approval may promote them into the sole manual baseline. / 生成坐标和 JPG 都只是
  pending；只有用户明确确认后才能进入唯一人工基线。
- Blind annotation must hide X5 Crop predictions and filename `pass` / `unknown`
  hints. Comparison mode becomes available only after manual coordinates are
  locked and cannot rewrite them. / 盲标注阶段隐藏程序预测与文件名状态提示；人工坐标
  锁定后才进入只读比较模式，比较结果不得回写人工事实。
- Aggregate observations from this work may guide later detector calibration,
  but the project may not become an input to its own reference. / 审阅中发现的规律可用于
  后续优化，但项目输出不能反过来生成自己的基准。

## Current Checkpoint / 当前检查点

- Branch / 分支：`main`.
- Pre-update handoff / 本次更新前交接：`4bc614fc`
  (`Set visual crop baseline handoff`). Always verify the live `HEAD` before
  resuming. / 恢复工作时必须重新核对现场 `HEAD`。
- Current report revision / 当前报告 revision：
  `cross_region_photo_edge_geometry`.
- The local source set contains 111 original TIFFs: 47 `135/full`,
  14 `135/partial`, 32 `120-66/partial`, 3 `120-67/full`,
  10 `half/full`, and 5 `half/partial`. The `Test/` layout is local evidence,
  not a tracked source contract. / 本地现有 111 张原始 TIFF；`Test/` 布局不是源码合同。
- The former `Test/135/full/unknown_X5_00010.tif` was deleted after its SHA-256
  exactly matched `unknown_X5_00004.tif`
  (`8db9b8d72dfe...`). The former `unknown_X5_00011.tif`
  (`cfad8fd05f59...`) is now the current `unknown_X5_00010.tif`; no
  `unknown_X5_00011.tif` remains. / 原 `00010` 与 `00004` 哈希完全相同，已删除；
  原 `00011` 已改名为当前 `00010`，当前不再存在 `00011`。
- The tooling audit is complete. Current owners are `tools/verify`,
  `tools/git/`, `tools/release/`, `tools/regression/compare.py`, and
  `tools/tests/`. / tools 已按职责收束为验证、Git、发布、报告比较和合同测试。
- At this documentation checkpoint, `tools/verify full` passed 826 tests,
  14 format/mode configuration checks, compilation, packaging, and V4.9
  contracts. This proves mechanical consistency only. / 当前文档检查点通过 826 项测试、
  14 组配置、编译、打包与 V4.9 合同；它只证明机械一致性。

## Gold Calibration Cohort / 黄金校准集

The user selected these nine originals as the first calibration cohort. The
descriptions below are selection rationale, not crop labels or confirmation.
Their identities must be rebound to the new manifest by full relative path and
SHA-256 before annotation.

用户已选择以下 9 张作为首批校准样片。下列描述只是选片理由，不是裁切标签或确认；开始
标注前必须用完整相对路径与 SHA-256 重新绑定到新 manifest。

| Group / 类别 | Source and rationale / 样片与理由 |
|---|---|
| `135/full` | `pass_X5_00027.tif`: clear standard negative / 清晰标准负片；`pass_X5_00035.tif`: lower-contrast positive / 较低对比正片 |
| `135/partial` | `pass_X5_00004.tif`: standard three frames starting from the right / 从右侧开始的标准三张；`unknown_X5_00003.tif`: centered start, touches neither side, lower contrast / 从中间开始且不靠两侧、对比较低 |
| `66/partial` | `pass_X5_00001.tif`: normally exposed positive / 正常曝光正片；`pass_X5_00030.tif`: normally exposed negative / 正常曝光负片 |
| `67/full` | `pass_X5_00001.tif` |
| `half/full` | `pass_X5_00002.tif`: normal exposure with unstable frame pitch / 曝光正常、片距不稳定 |
| `half/partial` | `pass_X5_00003.tif`: normally exposed strip starting from the right / 从右侧开始、曝光正常 |

The full paths are under their matching `Test/<format>/<mode>/` directories;
same basenames in different groups are distinct identities. / 完整路径位于对应
`Test/<format>/<mode>/`；不同类别中的同名文件不是同一身份。

## Blind Annotator Boundary / 盲标注器边界

- The annotator is not built yet. It will be a local-only interface under
  untracked `Test/manual_review/`, backed by generic TIFF decoding and a browser
  canvas. / 工具尚未建立；计划放在未跟踪的 `Test/manual_review/`，仅本地运行。
- Annotation mode shows the original overview, native-scale tiles, reversible
  display rotation, and explicit tonal aids. Only user clicks create observed
  boundary polylines and the source-safe polygon; there is no edge finding,
  snapping, or automatic inset. / 标注模式只负责原图显示、原生切片、可逆旋转和色调
  辅助；边界点与 safe polygon 全部来自用户点击，不自动找边、吸附或内缩。
- Drafts remain `pending_user_review` or `unresolved`. A separate explicit user
  confirmation creates `user_confirmed_no_bleed_crop` in the sole
  `manual_baseline.jsonl`. / 草稿保持 pending 或 unresolved；只有单独明确确认才写入
  唯一人工基线。
- The runtime, detector, tests, reports, and gates never read the manual
  baseline. Locked baseline rows are consumed only by an independent local
  comparison view. / 运行时与项目 Gate 不读取人工基线；锁定结果只供独立本地比较。

## Current Architecture Facts / 当前架构事实

- `FramePhysicalSpec` owns photo dimensions.
  `ScanCanvasPhysicalSpec` solely owns holder-scan dimensions. TIFF resolution
  tags are preserved metadata only. / 照片尺寸与片夹扫描画布由两个独立 typed owner
  保存；TIFF resolution 标签不参与检测。
- `ScanCanvasEvidence` resolves a known single-strip physical canvas from source
  pixel aspect and produces `CanvasPixelScale`. Unmatched or competing profiles
  remain typed unresolved; `135-dual` does not invent one physical canvas. /
  已知单条画布按像素比例匹配；未知、竞争和 dual-lane 状态不会被强行解析。
- `PhotoEdgePairEvidence` is the sole truth for source top/bottom edge identity.
  It binds the complete physical label and `FrameSizeMm`. / 照片上下边缘身份只有一个
  真相来源，并绑定完整物理规格。
- Local measurements are material-, scene-, and polarity-independent. Dense
  responses are temporary; reports retain only compact fragments, active/witness
  observations, feasible geometry, and typed outcomes. / 局部测量不猜材料、场景或
  明暗极性；报告不保存密集临时候选。
- Pair identity, transform usability, and mapped shared-axis safety are separate
  consumers. A failure in a later consumer does not rewrite earlier evidence. /
  边缘身份、变换可用性与共享短轴安全性分层判断。
- Source geometry uses one typed affine mapping. Rotation never triggers a
  second short-axis pixel observation. / 旋转只映射同一份 source geometry，
  禁止重新寻找短轴。
- `CandidateGate` assesses candidates; only `DecisionGate` creates final
  `PASS/REVIEW` and final reasons. / 最终状态与 reasons 只由 `DecisionGate` 创建。

Current runtime flow and numerical contracts live only in `ARCHITECTURE.md`;
this checkpoint must not duplicate them. / 当前运行流与数值合同只由
`ARCHITECTURE.md` 维护。

## Manual Review Reset / 人工审阅归零

There is currently no manual crop baseline, deskew baseline, photo-edge label
set, sample expectation, frame-slot reference, or human-confirmed machine result.
No old conclusion is current authority.

当前不存在人工裁切基线、deskew 基线、photo-edge 标签、sample expectation、
frame-slot reference 或 human-confirmed 机器结果；旧结论均不再具有权限。

- Old local review artifacts were removed from the workspace. A recoverable
  safety copy exists at
  `/private/tmp/x5crop-manual-review-reset-20260724`; it is historical material,
  not a truth source, and must not be imported into the new cycle. /
  旧审阅资产已移出工作区；临时安全副本只用于误删恢复，不得迁移旧标签。
- Runtime, tests, reports, and tools must never read a human-label whitelist. /
  运行时、测试、报告和工具不得读取人工白名单。
- Machine `supported`, `PASS`, hashes, manifests, and generated review images do
  not mean human-confirmed. / 机器结果、哈希、清单和审阅图都不等于人工确认。
- The next review cycle must define one current schema before writing labels.
  Authority must bind source SHA-256 and source-coordinate evidence; only an
  explicit user decision becomes a human label. / 下一轮先定义唯一 current schema，
  再以 source SHA-256 与原图坐标绑定用户明确判断。

## Validation Boundary And Open Risks / 验证边界与开放风险

- The cross-region detector has structural and synthetic coverage, but its
  thresholds and real-sample behavior have not been newly human-calibrated. /
  当前 detector 已完成结构与合成验证，但尚未用新人工标签校准真实样片。
- The new visual annotation cycle has not yet produced an approved coordinate,
  review sheet, or baseline record. / 新一轮肉眼标注尚未产生任何已确认坐标、审阅图或
  baseline 记录。
- The nine gold samples are selected but not yet rebound into a manifest,
  annotated, or user-confirmed. The blind annotator does not yet exist. /
  9 张黄金样片目前仅完成选片，尚未建立 manifest 身份、标注或确认；盲标注器尚未建立。
- Some source boundaries may remain visually ambiguous even after tonal and
  native-scale inspection. Accuracy outranks completing all 111 as resolved. /
  个别原图边界可能仍不可辨；准确性优先于强行让 111 张全部 resolved。
- Mechanical verification does not establish physical correctness. Any accuracy
  claim must cite original TIFF coordinates and a new explicit user review. /
  物理准确性必须由原 TIFF 坐标与新的用户审阅证明。

## Next Actions / 下一步

1. Freeze a new stable `S001–S111` manifest from the current sorted source paths
   and SHA-256 values; do not reuse an old ID mapping. / 按当前 111 张的路径排序与
   SHA-256 建立全新稳定编号，不复活旧 S 编号。
2. Define the sole current source-coordinate schema and build the local blind
   annotator without detector access. / 定义唯一 source-coordinate schema，并建立
   不接触 detector 的本地盲标注器。
3. Validate display-to-source coordinate round trips on
   `135/full/pass_X5_00027.tif` and vertical-raster
   `66/partial/pass_X5_00001.tif`, then let the user approve the interface. /
   先用一横一竖两张验证坐标回算与界面。
4. Blindly annotate the nine selected samples. Promote only explicit user
   confirmations; retain visual ambiguity as unresolved. / 盲标 9 张黄金样片，只提升
   用户明确确认的结果。
5. Improve X5 Crop against the locked gold set using general physical contracts,
   never sample whitelists. Evaluate fresh samples independently before viewing
   detector overlays; feed demonstrated failure classes into later calibration. /
   用通用物理合同打磨项目，再以全新样片盲测，禁止样片白名单与循环证明。
6. Run the current 111-sample full audit only after gold calibration, fresh blind
   validation, runtime profiling, and repository verification are satisfactory. /
   黄金集、全新盲测、性能和仓库验证稳定后，再进行 111 张全量审计。

## Exact Resume / 精确恢复

Run these read-only checks first:

```bash
git log -1 --oneline
git status --short
find Test -type f \( -iname '*.tif' -o -iname '*.tiff' \) | sort
find Test/135/full -type f \( -name 'unknown_X5_00004.tif' \
  -o -name 'unknown_X5_00010.tif' -o -name 'unknown_X5_00011.tif' \) | sort
find Test -type f \( -iname '*baseline*' -o -iname '*manual*' \
  -o -iname '*review*' -o -iname '*expectation*' \
  -o -iname '*reference*' \) | sort
rg 'REPORT_SCHEMA_REVISION' x5crop
```

Resume prompt / 恢复提示：

> 从当前 111 张原始 TIFF 建立全新 S001–S111 manifest，并搭建只依赖通用 TIFF 解码、
> 手工点击和可逆坐标换算的本地盲标注器。先用指定的一横一竖样片验证工具，再盲标用户
> 选定的 9 张黄金校准样片。标注时隐藏 X5 Crop 与 pass/unknown 提示；所有草稿保持
> pending 或 unresolved，只有用户明确确认才进入唯一人工基线。锁定后才进入只读程序比较。
