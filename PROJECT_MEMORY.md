# Project Memory / 项目记忆

Updated / 更新：2026-07-25

This is the sole cross-session checkpoint for X5 Crop. It is a concise map, not
an instruction source or completion proof. Current user intent, Git, source,
original TIFFs, current reports, Debug Analysis, and live command output remain
authoritative.

本文件是 X5 Crop 唯一跨会话检查点，只保存当前地图，不是指令或完成证明。当前用户目标、
Git、源码、原始 TIFF、current report、Debug Analysis 与现场命令始终优先。

## Current Objective / 当前目标

The manual-reference workspace is restarting from zero. Keep the current
111-source manifest and user-click annotator, remove all assistant-authored or
retired reference material, and collect any future baseline only through the
current direct-user-click schema.

manual reference 工作区从零重新开始。保留当前 111-source manifest 与用户点击 annotator，
移除全部模型生成或已退役的 reference 材料；以后只通过 current direct-user-click schema
重新建立 baseline。

- Do not send complete long TIFFs to model vision for coordinate authorship. /
  不再让模型通过完整长 TIFF 生成 reference 坐标。
- Do not restore, reconstruct, import, or migrate deleted assistant proposals
  or retired reference files. / 不恢复、不重建、不导入、不迁移已删除的模型草稿或旧
  reference 文件。
- Do not promote X5 Crop, OpenCV, SciPy, model vision, generated JPGs, hashes,
  or algorithm agreement into ground truth. / 项目输出、图像算法、生成物与算法一致均不是
  ground truth。
- Only source-SHA-bound original coordinates created and explicitly confirmed
  by the user, or an independently calibrated external measurement, may enter a
  baseline. Visually indeterminate geometry remains unresolved. / Baseline 只能
  接受用户直接点击并明确确认的原图坐标，或独立校准的外部测量；看不清保持 unresolved。
- Detector calibration is paused until the new user-confirmed baseline has
  representative coverage. / 新一轮用户确认 baseline 达到代表性覆盖前，不继续用样片
  调 detector。

## Verified Checkpoint / 已核对检查点

- Branch / 分支：`main`.
- Reset base / 本次归零起点：`7abdbd30`
  (`Avoid duplicate hook verification`); always check live `HEAD` when resuming.
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
- A local browser annotator exists under `Test/manual_review/annotator/`.
  Its current schemas are `x5crop_user_manual_proposal_v1` and
  `x5crop_user_manual_baseline_v1`; it accepts only direct user clicks and has
  no model/assistant suggestion import path. / 本地标注器已建立，当前只接受用户点击。
- Focused verification passed 20 annotator contracts, all 111 live source
  SHA-256 checks, and JavaScript syntax validation. Active state is
  `0 proposals / 0 confirmed baseline rows`. / 工具验证通过；活动 proposal 与确认
  baseline 均为 0。
- `tools/verify full` passed 826 tests and 14 format/mode configuration checks
  after this synchronization. This is mechanical evidence only. / 本次同步后完整
  verifier 通过 826 项测试与 14 组配置；它只证明机械一致性。
- `Test/manual_review/findings.md` contains no current visual finding. /
  当前没有样片视觉结论。
- All previous assistant-authored proposals and review artifacts have been
  deleted. No retired proposal, baseline, or review JPG is retained in the
  active workspace. / 旧模型 proposal 与审阅材料已全部删除；当前工作区不保留
  退役 proposal、baseline 或 review JPG。
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
current local Homebrew Python can import OpenCV 5.0.0 and SciPy 1.18.0, but X5
Crop V4.9 does not depend on them.

此前为 V5 预留的两个大依赖是 OpenCV 与 SciPy。当前本机 Homebrew Python 可导入
OpenCV 5.0.0 与 SciPy 1.18.0，但 V4.9 没有引入它们。

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
human-confirmed machine baseline. Active proposals and confirmed baseline rows
are both zero. No previous reference material remains; the next row must be
created afresh from a direct user click in the current schema.

当前没有任何有效人工或 human-confirmed baseline；活动 proposal 与确认 baseline 均为
0，也不再保留旧 reference 材料。下一条记录必须由用户在 current schema 中重新直接点击
产生。

## Validation Boundary And Open Risks / 验证边界与开放风险

- The annotator contracts prove identity, coordinate transforms, write
  authority, and file integrity only. They do not prove that any boundary is
  physically correct. / 工具通过只证明合同与文件一致，不证明边界正确。
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

1. Start a new blind pass from the retained 111-source manifest and current
   `x5crop_user_manual_proposal_v1` / `x5crop_user_manual_baseline_v1` schemas.
   Create coordinates only from direct user clicks and explicit confirmation;
   leave ambiguous geometry unresolved. / 从保留的 manifest 与 current schema
   开始全新盲标，只接受用户点击与明确确认，看不清则 unresolved。
2. Confirm representative gold-cohort frames before expanding the pass. Do not
   reconstruct or import any deleted reference material. / 先确认代表样片，再扩展
   审阅；不重建或导入任何已删除的 reference 材料。
3. If V5 is authorized, isolate and pin OpenCV/SciPy in the project environment,
   define their exact role, and keep automated geometry outside the baseline
   write path. / 若启动 V5，先隔离并锁定依赖，并保证自动几何无法写 baseline。
4. Only after an independent baseline exists should detector calibration,
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
python3 -B Test/manual_review/annotator/server.py verify
rg 'REPORT_SCHEMA_REVISION' x5crop
```

Resume prompt / 恢复提示：

> 从当前 111-source manifest 与用户点击专用 annotator 重新开始。活动 proposal 和
> baseline 均应为 0，旧 reference 材料不再存在。使用 current schema 从用户直接点击建立
> 第一批全新 reference；任何看不清的几何保持 unresolved，不恢复旧材料。
