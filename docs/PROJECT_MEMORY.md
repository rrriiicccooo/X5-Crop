# 项目记忆

更新：2026-07-30

这是 X5 Crop 唯一跨会话检查点。它只保存当前状态、已验证 receipt、验证边界、开放风险和
下一步；当前源码、Git、原 TIFF、current report、Debug Analysis 与现场命令输出始终
优先。运行合同见 [ARCHITECTURE.md](ARCHITECTURE.md)，版本历史见
[CHANGELOG.md](CHANGELOG.md)。

## 当前状态

- 当前开发版为 V4.9；稳定公开 Release 仍为 `v4.2.8`，本次没有创建新 Release。
- Partial auto 容量 slots 已完成原子切换：
  - full 使用 format 默认 slots；
  - partial explicit 严格服从用户权威 count；
  - partial auto 输出唯一匹配片夹对当前 format 的全部有效 slots，不推断或声明真实照片
    张数。
- Current runtime identity 为 `bounded_safe_crop_capacity_grid`。没有 feature flag、
  fallback、兼容 reader、双 schema、alias、shim 或第二套 detector。
- `ResolvedOutputSlots(lane_output_slot_counts)` 是唯一解析结果。总 slot 数只从 canonical
  lane counts 求和；candidate、final detection、report、manifest 与输出共同引用或派生
  该结果。
- `135-dual` 固定为 `(6, 6)`，按 `lane:0/1..6`、再 `lane:1/1..6` 输出；每张保存 global
  与 lane-local ordinal。
- 每个 lane 只搜索一个 resolved slot count。Score/tie-break 只决定构建顺序和诊断；
  output-equivalent proposals 才能 outward union，非等价 placement/ordinal/ownership
  classes 不会被静默排序选出赢家。
- 每个 P/O/K 截断都有 typed `GridOmissionSummary`。只有 omitted alternatives 全部被证明
  等价并进入 retained class 的 outward union 才不阻断；否则
  `grid_search_coverage = CONTRADICTED`。
- `CandidateGate` 只记录十项候选事实；第四项为 `output_slot_count`。只有
  `DecisionGate` 创建 `approved_auto`、`needs_review` 与 typed reasons。
- Approved 后 profile、slots、transform 与 boxes 不变；slots、safe/protected envelopes、
  final boxes、TIFF 数均等于派生总数。Review 的 TIFF 数为零。
- 每个 approved ROI 只从原图采样一次，写出后复读验证 TIFF pixels、dtype、
  axes/channels、ICC、resolution、metadata 与 NONE/LZW 无损压缩。I/O 错误保持独立
  `FailedInput` / terminal failure。

## Current identities

```text
detector kind            = bounded_safe_crop_capacity_grid
Grid algorithm           = bounded_ordered_capacity_grid_v5
Grid numeric prior       = safe_crop_prior_v1
calibration receipt      = x5crop_grid_calibration_receipt_v2
calibration receipt ID   = sha256:f6edbfd78d1711b361113abc952b37884bf594dd367ba22cd64f316e42f94738
report revision          = bounded_safe_crop_capacity_grid
run manifest             = x5crop_run_manifest_v2
acceptance result        = x5crop_safe_crop_acceptance_result_v2
acceptance summary       = x5crop_safe_crop_acceptance_summary_v2
coverage audit           = x5crop_safe_crop_coverage_audit_v2
fixed sample profile     = x5crop_fixed_sample_profile_v2
production performance  = x5crop_production_performance_v4
```

数值 prior 未改变。Confirmed geometry 只校准 prior 中心/区间并验证 containment，
provenance 保持 `user_confirmed_geometry`；它不成为 separator/photo-edge runtime
observation，也不证明 Grid。

## 2026-07-30 验证 receipt

### Tracked 与 focused contracts

- `python3 -m unittest discover -s tools/tests -p 'test_*.py'`：53/53 通过。
- Contracts 覆盖 input mapping、全部 catalog capacity、120-67 短片夹 2 slots、单容量
  Grid、score reversal、等价 union、非等价 class 阻断、P/O/K omission proof、count 1、
  blank、vertical、dual lane、120 双 component、contact/overlap、protection saturation、
  Gate reasons、TIFF terminal failure、current schemas 与 standalone source。
- `x5crop.configuration.consistency`：13 个 format/mode pairs 通过。

### 黄金 accuracy 与真实 coverage

- 九张 source-SHA-bound、用户确认 geometry 的黄金样片展开为 14 个场景：14/14 通过，
  14 个均为 `approved_auto`；12 个 `must_approve_safe` 全部批准，S055 explicit/auto 也
  均安全批准。
- Partial auto 容量：
  - S051、S055：6；
  - S062、S091：3；
  - S109：12。
- Golden comparator 使用 source-coordinate、严格递增的一对一 containment；所有 confirmed
  polygons 均被不可复用、顺序递增的 output footprints 完整包含。允许额外 blank slots。
- 111/111 blocking audit 通过：
  - 88/88 `pass_*` 全部 `approved_auto`，包括 S098；
  - 41/41 pass partial 全部批准，并精确输出匹配片夹容量；
  - 23 条 `unknown_*` 中 22 条批准，S111 因具体
    `output_slot_count` / `output_protection` Gate 阻断而 review；
  - 111 records 对应 107 个独立 source SHA，重复 SHA 已单列；
  - partial extra-slot distribution：
    `0:36, 1:3, 2:2, 3:2, 4:1, 5:4, 7:2, 10:1`。
- 九张黄金 Debug Analysis 与 S067 已人工检查，未见明显 inward loss、lane/ordinal 错位
  或异常跨片。该视觉检查只作 current output 审计，不建立或修改 baseline。

### 固定 profiling

- Sample：S062。
- Source SHA：
  `ed1e0aba8b78a8619ffe0cc14b855fdd87ebcc92f4c8c137da3fef8f7192a7f6`。
- Identity：`120-66/partial/auto`，profile `120_wide_224_5`，lane counts `(3,)`。
- Wall `2.804 秒`；detection `2.581 秒`。
- Measurement `4`，exact-cache hits `0`，candidate builds `2`，seeds `2`，
  states/transitions `4/8`，retained proposals `2`。
- 36 个 omitted alternatives 全部被等价 class 吸收，unresolved `0`；
  `search_incomplete=true` 仅为诊断，`omitted_outcome_risk=false`。
- Peak temporary memory `348,469,137 bytes`；hotspot 为 source-content components。

### 正式性能与 standalone

- 一个空 root 下完成 `cold`、`measured-1/2/3`，四次均 `--jobs 2`、固定 24 个真实输入，
  并实际写出、复读每个 TIFF。
- 每轮均为 24/24 completed、168 个 TIFF；九个 partial 输入相对 filename annotation
  多 25 个 slots。
- Cold `2.507 秒/输入`；measured 分别为 `2.494`、`2.502`、`2.499 秒/输入`；中位数
  `2.499 秒/输入`，通过 `<= 5.0 秒/张` 合同。
- 现场 managed sandbox 不允许 process worker，runtime 使用既有 thread fallback；上述
  receipt 仍覆盖 `--jobs 2` 的真实 TIFF 写出/复读，但正式公开 Release 前可在普通 macOS
  process-worker 环境再留一份对照。
- 使用唯一 builder `python3 -m tools.release.build --version 4.9` 构建
  `X5-Crop-v4.9.zip`。包包含 10 个 manifest entries、中文 UTF-8 文件名、可执行 launcher
  与 installer。
- 从最终 ZIP 解包的 standalone 对 S062 auto 实跑通过：profile
  `120_wide_224_5`、lane counts `(3,)`、3 个 TIFF，current report 与 TIFF read-back
  receipt 正常。

## 不可偏移的产品合同

- 成功标准是不内切真实照片内容，不是唯一恢复物理边界或复刻历史 boxes。
- Auto 的输出 slot 数是片夹容量，不是真实照片 count。额外 blank TIFF、完全空片的空白
  slots、向外多保留、相邻框重叠、inferred Grid、protection saturation 与 bounded shared
  pixels 均可接受。
- `needs_review` 只用于 protection 无法吸收的 ordinal/placement、primary ownership、
  omission coverage、containment、source/lane authority 或 output geometry 风险。
- Separator 缺失、等价 geometry、未 deskew 或邻片像素本身不能制造 review。
- Format、scan-canvas、scale、source content、separator、Grid、protection、Gate、
  finalization、output 与 report 各有唯一 owner，权限只向下游流动。
- Filename count/`pass`/`unknown` 只属于 validation cohort，永不进入 detector、prior、
  score、Gate 或 runtime selection。

## 验证边界与开放风险

- `real_holdout = unavailable`。当前 accuracy completion 只由九张黄金样片支撑。
- XPan、120-645、135-dual 及部分 format/mode/placement/interaction 缺少真实样片；
  coverage cell 保持 `real_sample_coverage = unavailable`。XPan 与 120-645 只有
  physical-rule synthetic coverage。
- `Test/` 是 ignored 的本地验收样片库；保留原 TIFF、111-source manifest、九张黄金
  source/marked/review/baseline 证据及必要 symlink。它不属于源码、Release 或 verifier
  的目录布局合同。
- Acceptance、audit、profiling、performance 与 package 检查是运行产物，不在 tracked
  tree 冒充永久真值。任何 detector、Gate、schema 或 package-source 变化都会使对应
  receipt 失效。
- 正常交付依赖 pre-commit staged hygiene 与 pre-push 唯一 full validation；Git 现场状态
  是最终交付 authority。

## 下一步

- 没有已知实现 blocker。V4.9 若准备公开 Release，应先在 release-target macOS 上复测
  process-worker 性能、复核包内安装流程，再由用户明确授权创建 GitHub Release。
- 若未来出现 named physical gap，只补该 gap 所需的 measurement、contract 或真实样片；
  不恢复被替代的 detector/schema、样片 whitelist 或 proof-only approve 标准。
