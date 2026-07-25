# Project Memory / 项目记忆

Updated / 更新：2026-07-26

This is the sole cross-session checkpoint for X5 Crop. It records the current
objective, verified state, validation boundary, open risks, and exact next
action—not architecture or history. Git, source, original TIFFs, current reports,
Debug Analysis, and live command output remain authoritative.

本文件是 X5 Crop 唯一跨会话检查点，只保存当前目标、已核对状态、验证边界、开放风险与
精确下一步，不重复架构或历史。Git、源码、原始 TIFF、current report、Debug Analysis
与现场命令始终优先。

## Current Objective / 当前目标

Use the completed user-confirmed golden baseline to calibrate and audit the V4.9
detector. The accepted geometry chain is:

使用已完成的用户确认黄金基线，校准并审计 V4.9 detector。已接受的几何主链为：

```text
observed shared long edges
→ deskew and shared short axis
→ paired long-axis frame edges
→ conservatively contained safe rectangles
→ output-only bleed
```

- The goal is a sufficiently accurate safe crop under calibrated directional
  tolerances, not mathematical zero-pixel error. / 目标是在方向性校准容差内形成足够准确的
  安全裁切，不追求数学 0 px。
- Keep typed evidence, one affine coordinate mapping, uncertainty,
  `CandidateGate`, `DecisionGate`, and typed unresolved. / 保留 typed evidence、
  唯一仿射坐标映射、uncertainty、两级 Gate 与 typed unresolved。
- Bleed is independent output expansion. It may cover tiny physical-edge and
  straight-line approximation error, but never conceal wrong base geometry. /
  bleed 只在输出阶段独立扩张，不能掩盖错误基础几何。
- Do not restore retired review mechanisms, historical schemas, aliases, shims,
  fallbacks, or runtime whitelists. / 不恢复已退役审阅机制、历史 schema、alias、
  shim、兼容 fallback 或 runtime 白名单。

## Verified Checkpoint / 已核对检查点

- Branch / 分支：`main`.
- Active runtime / 当前 runtime：`X5_Crop.py` V4.9.
- Report revision / 报告 revision：`cross_region_photo_edge_geometry`.
- Stable release / 稳定发布：`v4.2.8`.
- The local source library contains 111 untouched TIFFs: 47 `135/full`,
  14 `135/partial`, 32 `66/partial`, 3 `67/full`, 10 `half/full`, and
  5 `half/partial`. `manifest.jsonl` contains the same 111 source identities and
  nine gold markers. / 本地有 111 张未修改原 TIFF，manifest 一一绑定并标出 9 张黄金集。
- The manual-review evidence chain is complete: nine marked TIFF copies, nine
  native-resolution review JPGs, nine
  `x5crop_red_markup_fit_proposal_v1` records, and nine immutable
  `x5crop_user_confirmed_golden_baseline_v1` rows. / 人工审阅证据链已完成：
  9 张标注副本、9 张原生分辨率 JPG、9 条 proposal 与 9 条 confirmed baseline。
- `red_markup_converter.py verify` checks source/marked/JPG hashes, exact line
  counts, boundary order, in-bounds positive polygons, native JPG dimensions,
  stroke residuals, proposal snapshots, and all confirmed rows. / 本地 verifier
  检查完整 hash、线数、顺序、polygon、尺寸、拟合残差与 confirmed snapshot。
- Converter revision `preview_red_delta_robust_line_fit_v2` rejects a declared
  frame count when stronger extra boundary strokes exist; it cannot silently
  discard user markup. / converter v2 会拒绝与强红线数量矛盾的声明帧数，不能静默漏帧。

| ID | Group | Frames | Strip | Calibration role | Confirmed JPG SHA-256 |
|---|---|---:|---|---|---|
| `S027` | `135/full` | 6 | horizontal | `nominal_calibration` | `bf0dfe7f934dbdf69dc585e9a17007f5645107459232be5960c196d5d4fa3613` |
| `S035` | `135/full` | 6 | horizontal | `nominal_calibration` | `5f0194e6bab9c7a8d4dfc6a36c57e3cbb50865e0802be5fc6afebb8febb2b497` |
| `S051` | `135/partial` | 3 | horizontal | `nominal_calibration` | `288b6a247e2022e0525b0f139c671b701a829e40ebb8230ef244a408ab9f8b3f` |
| `S055` | `135/partial` | 4 | horizontal | `nominal_calibration` | `f5e54e3a305dee31ea91d05bb3f8a3397d77f3a84cb33ce3dd242a3017d1ea42` |
| `S062` | `66/partial` | 3 | vertical | `nominal_calibration` | `3dc83771a1d81a56ebb4bc0d329ecbd3b8b298a7945cce55b5db247806eeea87` |
| `S091` | `66/partial` | 3 | vertical | `nominal_calibration` | `d28f8fdbf95389037f2273a58df83ef6cc3a1509c6a66cfb77c2c0bcd2b3cd38` |
| `S094` | `67/full` | 3 | horizontal | `nominal_calibration` | `88e6470a8b535c4b0b8a680c11674a5a83d6553933ec389440002a82b5a96782` |
| `S098` | `half/full` | 12 | horizontal | `irregular_geometry_stress` | `6c346b94454b9ae030aa6908b3c2d7a427e28cd12dd7fef9e3f51faf29a56ca4` |
| `S109` | `half/partial` | 7 | horizontal | `nominal_calibration` | `fb824fd1335bd895f3f1e1ed6cd4cbd349117ced38bcb483f6e6f781987abb44` |

`S098` remains correct golden truth, but camera aging makes its frames
non-rectangular and pitch unstable. It is excluded from nominal tolerance
estimation and retained to verify that runtime does not force perpendicular
dividers, equal pitch, or automatic PASS. A rectangular output must be
conservatively contained inside its observed quadrilateral; otherwise it remains
typed REVIEW.

`S098` 的人工坐标仍是真值，但老化相机造成非矩形与不稳定片距。它不参与正常容差估计，
只用于验证 runtime 不强迫垂直、等片距或自动 PASS；矩形输出必须保守包含在观测四边形内，
否则保持 typed REVIEW。

## Current Manual Review Contract / 当前人工审阅合同

- Untouched source TIFFs own raster coordinates and source SHA-256. Marked copies
  contain only direct user strokes. / 未修改原 TIFF 拥有坐标与 source SHA；标注副本
  只保存用户直接笔迹。
- Proposal rows remain `pending_explicit_user_confirmation` observations even
  after a separate confirmed row exists. Only an explicit user confirmation of
  the exact review JPG may create baseline authority. / proposal 始终是 observation；
  只有用户明确确认确切 JPG，独立 baseline row 才获得权限。
- Each confirmed row binds the source SHA, marked-copy SHA, immutable proposal
  snapshot SHA, review JPG SHA, continuous source-pixel geometry, and confirmed
  integer polygon. / 每条 confirmed row 同时绑定 source、marked copy、proposal
  snapshot、JPG hash 与原图坐标。
- Model vision, OpenCV, SciPy, generated JPGs, hashes, residuals, or algorithm
  agreement cannot independently author truth. Ambiguous geometry remains
  unresolved. / 模型视觉与算法只能转换或验证一致性，不能独立创建真值。
- `nominal_calibration` estimates normal directional, containment, content-loss,
  and pitch tolerances. `irregular_geometry_stress` is held out from threshold
  estimation. / 正常子集用于估计阈值，压力样片不参与阈值统计。

## Clean Workspace Boundary / 干净工作区边界

Tracked current owners are root docs/launchers, `install/`, `x5crop/`, and
`tools/`. Historical snapshots live in Git history and tags; the redundant
tracked `archive/` tree has been removed.

受跟踪的 current owner 只有根文档/启动器、`install/`、`x5crop/` 与 `tools/`。
历史版本只由 Git history 与 tags 保存，不再维护重复 `archive/`。

`Test/manual_review/` intentionally retains only:

```text
README.md
findings.md
manifest.jsonl
red_markup_converter.py
red_markup_fit_proposals.jsonl
user_confirmed_golden_baseline.jsonl
gold_calibration_v1/   # 9 marked TIFF copies
review_jpg/            # 9 confirmed review JPGs
```

`Test/` is ignored local evidence, not a tracked source contract. Original TIFFs,
the nine marked copies, confirmed JPGs, proposals, baseline, manifest, converter,
and two local explanations are intentional. Generated outputs, caches,
`.DS_Store`, and temporary files are not.

`Test/` 是 ignored 本地证据，不是 tracked source contract。原 TIFF、九张标注副本、
确认 JPG、proposal、baseline、manifest、converter 与两份说明必须保留；生成输出、
cache、`.DS_Store` 与临时文件不保留。

## Validation Boundary And Open Risks / 验证边界与开放风险

- Nine user-confirmed rows establish the project's practical safe no-bleed
  reference; they are not an independently measured mathematical oracle. /
  九条确认记录建立项目实用权威，不声称是独立物理测量的数学 oracle。
- The current production detector has not yet been measured or calibrated
  against this completed baseline. Do not call current PASS geometry accurate
  merely because `tools/verify` is green. / 当前 detector 尚未对完整黄金基线量化；
  full verifier 通过不等于真实样片几何准确。
- Calibration must compare source-coordinate polygons through the sole transform
  mapping and preserve directional error: unsafe outward crossing, inward
  content loss, normal distance, angle, and containment must not collapse into
  one undirected score. / 校准必须通过唯一坐标映射比较，并保留方向性误差。
- OpenCV and SciPy are local calibration/conversion dependencies only. V4.9
  runtime and release dependencies remain NumPy, tifffile, imagecodecs, and
  Pillow. / OpenCV 与 SciPy 尚未进入 V4.9 runtime 或 release。
- The tracked test audit found no duplicate test bodies, empty test modules,
  unused public support owners, or active Python modules without static incoming
  ownership. The 826 current tests remain; no test was deleted speculatively. /
  测试审计未发现可证明的重复或孤立 owner，826 项 current tests 全部保留。

## Exact Next Action / 精确下一步

1. Define one read-only calibration comparison contract from production output
   to confirmed source-coordinate polygons, including the existing deskew mapping.
   / 先定义 production output 到 confirmed 原图 polygon 的只读比较合同。
2. Measure the eight `nominal_calibration` samples without tuning. Record
   per-edge signed normal distance, angle, unsafe outward crossing, inward
   content loss, containment, status/reasons, and geometry resolution. /
   先测量八张正常样片，不先调参。
3. Derive directional acceptance tolerances only from the nominal subset, then
   validate `S098` separately as held-out irregular stress. / 只用正常子集定容差，
   再单独验证 S098。
4. After a focused failing contract identifies one production gap, repair the
   canonical owner, compare current-schema reports and Debug Analysis, and rely
   on the next push hook for full verification. / 发现具体 gap 后再修 canonical owner；
   最终 full 验证交给 push hook。

Resume checks / 恢复检查：

```bash
git log -1 --oneline
git status --short
python3 -B Test/manual_review/red_markup_converter.py verify
wc -l Test/manual_review/manifest.jsonl
wc -l Test/manual_review/red_markup_fit_proposals.jsonl
wc -l Test/manual_review/user_confirmed_golden_baseline.jsonl
rg 'REPORT_SCHEMA_REVISION' x5crop
```

Resume prompt / 恢复提示：

> 从 9/9 user-confirmed 黄金基线继续：8 张 `nominal_calibration`，S098 为
> `irregular_geometry_stress`。先建立 production output 到 confirmed 原图 polygon
> 的只读方向性比较，不先放宽 detector；随后用 named TIFF、current report 与
> Debug Analysis 定位第一个真实 gap。
