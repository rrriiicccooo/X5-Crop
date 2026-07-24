# Project Memory / 项目记忆

Updated / 更新：2026-07-24

This is the sole cross-session checkpoint for X5 Crop. It is a concise map, not
an instruction source, runtime input, or completion proof. Current user intent,
Git, source, original TIFFs, current reports, Debug Analysis, and live command
output remain authoritative.

本文件是 X5 Crop 唯一的跨会话检查点，只保存简短地图，不是指令、运行时输入或完成证明。
当前用户目标、Git、源码、原始 TIFF、current report、Debug Analysis 与现场命令始终优先。

## Current Objective / 当前目标

The immediate task is to build a new no-bleed manual crop baseline for all 112
original TIFF samples through independent visual inspection, without using X5
Crop detection, reports, Debug Analysis, or retired labels to choose geometry.

当前任务是对全部 112 张原始 TIFF 进行独立肉眼式检查，标出准确且无 bleed 的裁切位置并
生成 JPG 供用户审阅。不得使用 X5 Crop detector、report、Debug 或旧标签来决定坐标。

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
- Aggregate observations from this work may guide later detector calibration,
  but the project may not become an input to its own reference. / 审阅中发现的规律可用于
  后续优化，但项目输出不能反过来生成自己的基准。

## Current Checkpoint / 当前检查点

- Branch / 分支：`main`.
- Structural implementation checkpoint / 结构实现检查点：`7827dda1`
  (`Audit tooling and reset manual review`). Always verify the live `HEAD`
  before resuming. / 恢复工作时必须重新核对现场 `HEAD`。
- Current report revision / 当前报告 revision：
  `cross_region_photo_edge_geometry`.
- The local source set contains 112 original TIFFs: 48 `135/full`,
  14 `135/partial`, 32 `120-66/partial`, 3 `120-67/full`,
  10 `half/full`, and 5 `half/partial`. The `Test/` layout is local evidence,
  not a tracked source contract. / 本地保留 112 张原始 TIFF；`Test/` 布局不是源码合同。
- The tooling audit is complete. Current owners are `tools/verify`,
  `tools/git/`, `tools/release/`, `tools/regression/compare.py`, and
  `tools/tests/`. / tools 已按职责收束为验证、Git、发布、报告比较和合同测试。
- At this documentation checkpoint, `tools/verify full` passed 826 tests,
  14 format/mode configuration checks, compilation, packaging, and V4.9
  contracts. This proves mechanical consistency only. / 当前文档检查点通过 826 项测试、
  14 组配置、编译、打包与 V4.9 合同；它只证明机械一致性。

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
- Some source boundaries may remain visually ambiguous even after tonal and
  native-scale inspection. Accuracy outranks completing 112 resolved entries. /
  个别原图边界可能仍不可辨；准确性优先于强行让 112 张全部 resolved。
- Mechanical verification does not establish physical correctness. Any accuracy
  claim must cite original TIFF coordinates and a new explicit user review. /
  物理准确性必须由原 TIFF 坐标与新的用户审阅证明。

## Next Actions / 下一步

1. Freeze a new stable `S001–S112` manifest from sorted source paths and
   SHA-256 values; do not reuse an old ID mapping. / 按当前路径与 SHA-256 建立新清单，
   不复活旧 S 编号权限。
2. Define one current-only source-coordinate schema for no-bleed frame crop
   geometry and pending review state. / 定义唯一的新 source-coordinate schema。
3. Produce a small layout pilot, obtain user approval of review readability,
   then visually annotate all 112 originals and generate one primary review JPG
   per sample with native-scale detail panels where necessary. / 先确认版式，再完成
   112 张独立肉眼标注与审阅 JPG。
4. Perform a second visual pass, record unresolved cases honestly, and write a
   concise findings report for detector improvement. / 二次肉眼复核，并记录有助于项目的
   真实规律。
5. After the user reviews the JPGs, promote only explicitly approved entries
   into one manual baseline; pending or rejected proposals remain outside it. /
   用户确认后才写入唯一人工基线。

## Exact Resume / 精确恢复

Run these read-only checks first:

```bash
git log -1 --oneline
git status --short
find Test -type f \( -iname '*.tif' -o -iname '*.tiff' \) | sort
find Test -type f \( -iname '*baseline*' -o -iname '*manual*' \
  -o -iname '*review*' -o -iname '*expectation*' \
  -o -iname '*reference*' \) | sort
rg 'REPORT_SCHEMA_REVISION' x5crop
```

Resume prompt / 恢复提示：

> 不使用 X5 Crop 脚本、report、Debug 或旧人工标签来决定几何；独立肉眼检查全部
> 112 张原始 TIFF，画出无 bleed 的 source-coordinate 裁切位置并生成 JPG 供我审阅。
> 所有结果先保持 pending，看不清则 unresolved；只有我的明确确认才能进入人工基线。
