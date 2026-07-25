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
- The user marked `S027` (`135/full/pass_X5_00027.tif`) and `S062`
  (`66/partial/pass_X5_00001.tif`) in red. Preview preserved raster dimensions
  and top-left orientation while rewriting RGB TIFFs as RGBA. / 用户已标注 S027
  与 S062；Preview 保持尺寸和方向，只把 RGB TIFF 改写为 RGBA。
- `Test/manual_review/red_markup_converter.py` uses source-vs-marked RGB deltas,
  NumPy, tifffile/imagecodecs, OpenCV, SciPy, and Pillow. It does not inspect the
  complete TIFF through model vision or import the production detector. /
  新转换器完全本地运行，不消费模型视觉或 production detector。
- `S027` recovered 183,941 red pixels, two shared edges, twelve short boundaries,
  and six polygons. Maximum shared-edge MAD is `0.136 px`; parallel angle
  difference is `0.0140°`; maximum divider perpendicular error is `0.1387°`. /
  S027 已恢复 2+12 条线和 6 个 polygon，拟合数值如上。
- `S062` recovered 85,005 red pixels, two shared edges, six short boundaries,
  and three polygons. Maximum shared-edge MAD is `0.125 px`; parallel angle
  difference is `0.0140°`; maximum divider perpendicular error is `0.0493°`. /
  S062 已恢复 2+6 条线和 3 个 polygon，拟合数值如上。
- Native-resolution review files are
  `review_jpg/S027_red_markup_fit.jpg` (`17263×2397`) and
  `review_jpg/S062_red_markup_fit.jpg` (`2797×9899`). Red is recovered user
  markup, cyan is the fitted shared edge, green is the fitted polygon, and
  yellow marks intersections. / 两张原生分辨率复核图已生成，颜色职责固定。
- Exact pending review JPG SHA-256 values are
  `bf0dfe7f934dbdf69dc585e9a17007f5645107459232be5960c196d5d4fa3613`
  for S027 and
  `3dc83771a1d81a56ebb4bc0d329ecbd3b8b298a7945cce55b5db247806eeea87`
  for S062. User confirmation must refer to these exact artifacts. / 用户确认必须
  对应上述确切复核图。
- `red_markup_fit_proposals.jsonl` contains two
  `x5crop_red_markup_fit_proposal_v1` records, both
  `pending_explicit_user_confirmation`. There is still no confirmed baseline
  row. / 当前只有两条待用户明确确认的 proposal，confirmed baseline 仍为 0。
- The browser blind selector, launcher, machine candidates, browser pending
  proposal, old blind-review JPG, caches, and local `.DS_Store` residue were
  removed. / 浏览器盲选器及其机器候选、遗留 proposal、旧图和缓存已删除。
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

- The fit verifier proves source/marked hashes, exact line counts, polygon shape,
  native JPG dimensions, and low stroke-fit residuals. It does not prove the
  selected physical boundary. / 拟合 verifier 只证明 hash、线数、polygon、JPG 尺寸与
  笔迹拟合残差，不证明物理边缘选择。
- Preview-associated alpha rewriting creates red-like RGB deltas in some image
  content. The converter therefore fits the outermost continuous stroke per axis
  coordinate rather than clustering every red-delta pixel. Both horizontal S027
  and vertical S062 pass this contract. / Preview 的 associated alpha 会在少量画面
  内容中形成伪红差；转换器按每个轴坐标的最外连续笔迹拟合，不能聚类全部红像素。
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

1. The user inspects `S027_red_markup_fit.jpg` and
   `S062_red_markup_fit.jpg` at native pixels and explicitly confirms both, or
   identifies the sample/frame/edge that must be redrawn. / 用户先原生像素审阅两张 JPG，
   明确确认，或指出需重画的样片、Frame 与边。
2. On explicit confirmation, freeze the two current proposals without
   recomputing them and write source-SHA-bound rows in
   `x5crop_user_confirmed_golden_baseline_v1`. / 确认后原样冻结当前 proposal，
   不重新拟合，再写入目标 baseline schema。
3. The user marks the remaining seven gold copies with the same red-only
   protocol; run the converter and require explicit JPG confirmation for each. /
   剩余七张沿用同一红线协议和逐图确认。
4. Calibrate acceptance tolerances from the complete confirmed cohort using
   normal-distance edge error, parallel/perpendicular angle error, safe
   containment, and content loss. Bleed stays separate. / 完成黄金集后再按法向距离、
   角度、安全包含与内容损失校准容差，bleed 独立。
5. Only after representative confirmed coverage should detector calibration,
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

> 从 S027 与 S062 两张 `pending_explicit_user_confirmation` 红线拟合 proposal 继续。
> 先让用户审阅两张原生分辨率 JPG；只有明确确认后才原样冻结为
> `x5crop_user_confirmed_golden_baseline_v1`。盲选器与机器候选已删除，不恢复旧材料。
