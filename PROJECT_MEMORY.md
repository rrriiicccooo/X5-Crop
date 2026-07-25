# Project Memory / 项目记忆

Updated / 更新：2026-07-25

This is the sole cross-session checkpoint for X5 Crop. It is a concise map, not
an instruction source or completion proof. Current user intent, Git, source,
original TIFFs, current reports, Debug Analysis, and live command output remain
authoritative.

本文件是 X5 Crop 唯一跨会话检查点，只保存当前地图，不是指令或完成证明。当前用户目标、
Git、源码、原始 TIFF、current report、Debug Analysis 与现场命令始终优先。

## Current Objective / 当前目标

Build a practical no-bleed golden baseline from user-drawn red geometry on copied
gold TIFFs. A local converter recovers those strokes against the untouched
source, fits their centers in original coordinates, and renders a native-resolution
review JPG. The fit remains a proposal until the user explicitly confirms that
named JPG.

通过用户在黄金 TIFF 副本上直接绘制的红线，建立实用的无 bleed 黄金基准。转换器只在本地
对未修改原图做像素差、在原图坐标拟合笔迹中心，并生成原生分辨率 JPG；用户明确确认指定
JPG 前，拟合始终只是 proposal。

- Do not send complete long TIFFs to model vision for coordinate authorship. /
  不再让模型通过完整长 TIFF 生成 reference 坐标。
- Do not restore the retired blind selector, machine candidates, browser
  proposals, old references, or runtime whitelists. / 不恢复已退役盲选器、机器候选、
  浏览器 proposal、旧 reference 或 runtime 白名单。
- Red-stroke residuals, line parallelism, JPG generation, hashes, or algorithm
  agreement prove conversion consistency only; they do not confirm the physical
  crop. / 红线残差、平行度、JPG、hash 与算法一致只证明转换一致，不确认物理裁切。
- Only source-SHA-bound fitted coordinates explicitly confirmed by the user, or
  an independently calibrated external measurement, may enter the baseline. /
  只有绑定 source SHA、经用户明确确认的拟合坐标或独立校准外部测量才可进入 baseline。
- Detector calibration is paused until the new user-confirmed baseline has
  representative coverage. / 新一轮用户确认 baseline 达到代表性覆盖前，不继续用样片
  调 detector。
- The target is a sufficiently accurate safe crop, not mathematical zero error.
  Bleed remains a separate output expansion and cannot conceal a wrong base
  geometry. / 目标是足够准确的安全裁切，不是数学零误差；bleed 是独立输出扩张，不能
  掩盖错误的基础几何。
- Accepted combined direction / 已接受组合方向：
  shared top/bottom edges → deskew/shared short axis → paired long-axis edges →
  safe rectangles → output-only bleed; vertical strips use the rotated equivalent.
- Keep current typed evidence, the sole affine coordinate mapping, uncertainty,
  `CandidateGate`, `DecisionGate`, and typed unresolved. Gold calibration will
  define directional tolerances for normal-distance error, angle, unsafe outward
  crossing, inward content loss, and containment; it will not create a single
  undirected score. / 保留当前 typed evidence、唯一坐标映射、uncertainty、两级 Gate 与
  unresolved；黄金集按法向误差、角度、危险外越界、向内内容损失与 containment 校准。

## Verified Checkpoint / 已核对检查点

- Branch / 分支：`main`.
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
- `Test/manual_review/gold_calibration_v1/` contains clone copies of all nine
  gold sources with their format/mode layout preserved. The untouched originals
  remain the SHA and coordinate authority. / 九张黄金副本已按 format/mode 保存，未修改
  原图仍是 SHA 与坐标权威。
- The user marked all nine gold copies in red. Preview preserved each source's
  raster dimensions and top-left orientation while rewriting RGB TIFFs as RGBA.
  / 用户已完成全部九张黄金副本的红线标注；Preview 保持原图尺寸与左上方向，只把
  RGB TIFF 改写为 RGBA。
- `Test/manual_review/red_markup_converter.py` uses source-vs-marked RGB deltas,
  NumPy, tifffile/imagecodecs, OpenCV, SciPy, and Pillow. It does not inspect the
  complete TIFF through model vision or import the production detector. /
  新转换器完全本地运行，不消费模型视觉或 production detector。
- `red_markup_fit_proposals.jsonl` contains nine source/marked/JPG-SHA-bound
  `x5crop_red_markup_fit_proposal_v1` records. Every proposal remains
  `pending_explicit_user_confirmation`; confirmation authority lives only in the
  separate baseline file. / 当前有九条绑定 source、marked copy 与复核 JPG hash 的
  proposal；proposal 本身始终是 pending，确认权限只存在于独立 baseline 文件。
- The user explicitly confirmed the exact current `S027` and `S062` JPGs.
  `user_confirmed_golden_baseline.jsonl` now contains two immutable
  `x5crop_user_confirmed_golden_baseline_v1` rows: six frames for `S027` and
  three for `S062`. Repeating confirmation is byte-idempotent, and `fit` refuses
  to recompute either confirmed sample. / 用户已明确确认当前确切的 S027 与 S062
  JPG；baseline 现有 2 行，重复确认不改字节，且 converter 拒绝重新拟合已确认样片。
- All nine native-resolution review JPGs exist. Red is recovered user markup,
  cyan is the fitted shared edge, green is the fitted polygon, and yellow marks
  intersections. Exact artifact identities and states are:

| ID | Group | Frames | Strip | State | Review JPG SHA-256 |
|---|---|---:|---|---|---|
| `S027` | `135/full` | 6 | horizontal | confirmed | `bf0dfe7f934dbdf69dc585e9a17007f5645107459232be5960c196d5d4fa3613` |
| `S035` | `135/full` | 6 | horizontal | pending | `5f0194e6bab9c7a8d4dfc6a36c57e3cbb50865e0802be5fc6afebb8febb2b497` |
| `S051` | `135/partial` | 3 | horizontal | pending | `288b6a247e2022e0525b0f139c671b701a829e40ebb8230ef244a408ab9f8b3f` |
| `S055` | `135/partial` | 3 | horizontal | pending | `730573792c7f94bda95b6ef4543e9df39a1829f2361caf56c9abba989528df56` |
| `S062` | `66/partial` | 3 | vertical | confirmed | `3dc83771a1d81a56ebb4bc0d329ecbd3b8b298a7945cce55b5db247806eeea87` |
| `S091` | `66/partial` | 3 | vertical | pending | `d28f8fdbf95389037f2273a58df83ef6cc3a1509c6a66cfb77c2c0bcd2b3cd38` |
| `S094` | `67/full` | 3 | horizontal | pending | `88e6470a8b535c4b0b8a680c11674a5a83d6553933ec389440002a82b5a96782` |
| `S098` | `half/full` | 12 | horizontal | pending | `6c346b94454b9ae030aa6908b3c2d7a427e28cd12dd7fef9e3f51faf29a56ca4` |
| `S109` | `half/partial` | 7 | horizontal | pending | `fb824fd1335bd895f3f1e1ed6cd4cbd349117ced38bcb483f6e6f781987abb44` |

  The hashes above, rather than filenames alone, identify what the user reviews.
  / 上述 hash 而非文件名本身，定义用户实际确认的 artifact。
- The browser blind selector, launcher, machine candidates, browser pending
  proposal, old blind-review JPG, and caches remain removed. / 浏览器盲选器及其
  机器候选、遗留 proposal、旧图和缓存保持删除。
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
now used only by the ignored local red-markup converter; X5 Crop V4.9 runtime
still does not depend on them.

此前为 V5 预留的两个大依赖是 OpenCV 与 SciPy。当前本机 Homebrew Python 可导入
完整数值栈；OpenCV 与 SciPy 目前只用于本地红线转换器，V4.9 runtime 没有引入它们。

- OpenCV can provide mature gradients, contours, line fitting, subpixel
  refinement, transforms, and drawing. / OpenCV 可提供成熟边缘、轮廓、直线拟合、
  亚像素修正、变换与绘制。
- SciPy can provide filtering, interpolation, optimization, robust fitting, and
  statistical uncertainty calculations. / SciPy 可提供滤波、插值、优化、稳健拟合与
  不确定度计算。
- They can process full TIFFs locally without consuming model context and can
  improve candidate generation or measurement reproducibility. They cannot
  reveal an occluded or visually ambiguous physical edge, prove semantic edge
  identity, or create an absolute oracle. Agreement between them is still
  machine consensus over the same pixels. / 它们能避免模型上下文问题并提高候选与
  测量复现性，但不能看见被遮挡或不可辨的真实边缘，也不能形成绝对 oracle。

## Current Manual Review Contract / 当前人工审阅合同

- Proposal schema / 拟合 proposal：
  `x5crop_red_markup_fit_proposal_v1`.
- Target baseline schema / 目标 baseline：
  `x5crop_user_confirmed_golden_baseline_v1`.
- User markup is drawn only on the gold copy. The converter binds the recovered
  fit to both the untouched source SHA-256 and marked-copy SHA-256. / 用户只修改
  黄金副本；转换结果同时绑定未修改原图与标注副本 SHA。
- Continuous line equations and polygon intersections remain in original raster
  pixel-center coordinates. Proposed integer boundaries are derived by nearest
  rounding and remain pending with the fit. / 连续线与交点保存在原图像素中心坐标；
  nearest-rounding 整数边界随 proposal 一起等待确认。
- A successful conversion or verifier never changes proposal status. Only an
  explicit user confirmation naming the review JPG may create baseline rows. /
  程序成功不会提升权限；只有用户明确确认指定复核 JPG 才能写 baseline。
- The project-authoritative baseline represents the user's safe no-bleed target
  within practical tolerance. It is not a claim of mathematical zero error or
  an independently measured physical oracle. / 项目权威 baseline 表示用户确认的实用
  安全无 bleed 目标，不声称数学零误差或独立物理 oracle。

## Validation Boundary And Open Risks / 验证边界与开放风险

- The fit verifier proves all nine source/marked/JPG hashes, exact line counts,
  boundary order, in-bounds positive polygons, native JPG dimensions, and
  low stroke-fit residuals; it also verifies both confirmed baseline snapshots.
  It does not prove the selected physical boundary. / verifier 已检查九张的 hash、
  线数、boundary 顺序、界内正面积 polygon、原生 JPG 尺寸与两条 confirmed snapshot；
  仍不证明物理边缘选择。
- Preview-associated alpha rewriting creates red-like RGB deltas in some image
  content. The converter therefore fits the outermost continuous stroke per axis
  coordinate rather than clustering every red-delta pixel. Both horizontal S027
  and vertical S062 pass this contract. / Preview 的 associated alpha 会在少量画面
  内容中形成伪红差；转换器按每个轴坐标的最外连续笔迹拟合，不能聚类全部红像素。
- Partial-strip shared edges are supported only between the first and last
  annotated frame boundaries; a synthetic contract covers this rule. `S098`
  uses a Hough long-stroke fallback because one slanted boundary overlaps its
  neighbor in axis projection; a separate overlapping-divider contract covers
  that recovery path. These are conversion mechanics, not physical evidence. /
  partial strip 的共享边只使用首尾 frame boundary 间的支持区；S098 因斜线投影重叠
  使用 Hough fallback。两条 synthetic contract 只保证转换机制，不增加物理证据。
- JPG is only the human review surface; coordinates are recovered from the TIFF
  delta, never measured from lossy JPEG pixels. / JPG 只供人工复核，坐标不从有损 JPG
  反测。
- Direct user markup and confirmation can establish a practical authoritative
  reference, but visually indeterminate geometry remains unresolved. Independent
  physical measurement is still required for mathematical certainty. / 人工标注与
  确认可建立实用权威；不可辨几何仍 unresolved，数学真值仍需独立物理测量。
- `Test/` is ignored, so a clean Git worktree does not mean the local review
  workspace is empty. / Git clean 不代表 `Test/manual_review/` 为空。
- Historical `/private/tmp/x5crop-*` diagnostic and safety directories were
  inventoried but left untouched; some are deliberate recovery copies. /
  `/private/tmp` 中的历史诊断与安全副本未删除。
- Mechanical verifier success never establishes named-TIFF geometry. /
  全量 verifier 通过不等于真实样片物理正确。

## Next Decision And Actions / 下一决策与行动

1. The user inspects `S035`, `S051`, `S055`, `S091`, `S094`, `S098`, and `S109`
   review JPGs at native pixels and either confirms the exact current artifacts
   or names the sample/frame/edge that must be redrawn. / 用户以原生像素审阅剩余七张
   JPG，确认当前确切 artifact，或指出需重画的样片、Frame 与边。
2. On explicit confirmation, promote the unchanged proposal snapshots into
   `x5crop_user_confirmed_golden_baseline_v1`; never recompute an already
   confirmed sample. / 明确确认后原样提升 proposal snapshot，不重新拟合已确认样片。
3. Calibrate acceptance tolerances from the complete confirmed cohort using
   normal-distance edge error, parallel/perpendicular angle error, safe
   containment, and content loss. Bleed stays separate. / 完成黄金集后再按法向距离、
   角度、安全包含与内容损失校准容差，bleed 独立。
4. Only after representative confirmed coverage should detector calibration,
   performance profiling, and the 111-sample audit resume. / 有代表性 confirmed
   baseline 后再恢复 detector 调整、性能与 111 样片审计。

## Exact Resume / 精确恢复

Run these read-only checks first:

```bash
git log -1 --oneline
git status --short
find Test -type f \( -iname '*.tif' -o -iname '*.tiff' \) | sort
wc -l Test/manual_review/manifest.jsonl
find Test/manual_review -maxdepth 4 -type f | sort
python3 -B Test/manual_review/red_markup_converter.py verify
rg 'REPORT_SCHEMA_REVISION' x5crop
```

Resume prompt / 恢复提示：

> 从 9 条红线拟合 proposal、2 条 confirmed baseline（S027、S062）与 7 张待确认
> JPG 继续。先让用户审阅 S035、S051、S055、S091、S094、S098、S109 的当前确切
> 原生分辨率 JPG；只有明确确认后才原样提升为
> `x5crop_user_confirmed_golden_baseline_v1`。盲选器与机器候选已删除，不恢复旧材料。
