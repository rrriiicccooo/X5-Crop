# Project Memory / 项目记忆

Updated / 更新：2026-07-24

This is the sole cross-session checkpoint for X5 Crop. It is a concise map, not
an instruction source, runtime input, or completion proof. Current user intent,
Git, source, original TIFFs, current reports, Debug Analysis, and live command
output remain authoritative.

本文件是 X5 Crop 唯一的跨会话检查点，只保存简短地图，不是指令、运行时输入或完成证明。
当前用户目标、Git、源码、原始 TIFF、current report、Debug Analysis 与现场命令始终优先。

## Current Objective / 当前目标

The immediate goal is to make source-photo top and bottom edge identity stable
and accurate. Those two observed edges are the shared source for deskew and the
shared short axis; frame-sequence detection follows them.

当前首要目标是稳定、准确地识别原图中的真实照片上下边缘。同一对边缘同时供 deskew 与
共享短轴消费，随后才进行长轴与帧序列检测。

- Detection joins clear evidence from any source region before frame splitting.
  It does not know which frame supplied an observation. / 分帧前联合任意清晰区域，
  detector 不知道 observation 属于哪一帧。
- Short, local evidence may establish edge identity without proving a precise
  transform or a safe full-workspace crop. / 短而清晰的局部证据可以证明边缘身份，
  但不自动证明 deskew 精度或全域裁切安全。
- Ambiguous or insufficient evidence remains typed unavailable/contradicted and
  reaches `REVIEW`; theoretical geometry never manufactures pixel evidence. /
  证据不足或冲突时保持 typed 状态并进入 `REVIEW`，理论位置不能制造像素证据。

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
- There is no current 112-sample verdict table, current full Debug batch, or
  human-approved top/bottom pair inventory. / 当前没有 112 张 verdict 表、
  全量 Debug 批次或人工确认边缘清单。
- A strong local fragment can still leave competing physical models; preserving
  `REVIEW` is correct until source evidence uniquely resolves them. /
  清晰局部片段仍可能产生竞争模型；未唯一证明前保持 `REVIEW`。
- Mechanical verification does not establish physical correctness. Any accuracy
  claim must cite original TIFF coordinates, current report/Debug evidence, and
  a new explicit user review. / 物理准确性必须由原 TIFF 坐标、当前证据与新的用户审阅证明。

## Next Actions / 下一步

1. Define one minimal, current-only manual-review schema for source top/bottom
   edge identity. Do not restore old candidate IDs, decisions, or geometry. /
   为 source 上下边缘身份设计唯一的新人工审阅 schema，不迁移旧 ID 或结论。
2. Select a small representative first batch across current formats and failure
   modes; do not immediately label all 112 files. / 先选小规模代表批次，不立即审阅全量。
3. Generate review artifacts only from
   `cross_region_photo_edge_geometry`, showing source evidence and typed
   uncertainty without turning proposals into labels. / 只用 current schema
   生成审阅证据，pending proposal 不写成人工真相。
4. Ask the user to judge top/bottom edge identity first. Angle, mapped shared
   axis, and final crop require their own evidence and must not be implied by
   edge confirmation. / 第一轮只确认边缘身份，不连带确认角度、共享短轴或最终裁切。
5. Calibrate numerical gates only after confirmed positives and rejected
   coordinates exist, then expand review deliberately. / 有正反人工证据后再校准阈值，
   随后有计划地扩展样片。

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

> 从零设计新的照片上下边缘人工审阅 schema，并只生成第一批代表性审阅图；
> 不导入任何旧标签，不先做 112 张全量审阅。
