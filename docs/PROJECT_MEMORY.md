# 项目记忆

更新：2026-08-01

这是 X5 Crop 唯一跨会话检查点。它只保存当前目标、已验证检查点、验证边界、开放风险和
精确下一步；当前源码、Git、原 TIFF、current report、Debug Analysis 与现场命令输出始终
优先。运行合同见 [ARCHITECTURE.md](ARCHITECTURE.md)，版本历史见
[CHANGELOG.md](CHANGELOG.md)。

## 当前状态

- 当前开发版为 V4.9；稳定公开 Release 仍为 `v4.2.8`，尚未创建 V4.9 Release。
- 功能检查点为 `f3990e9e`：完整 source-coordinate 照片几何实现已经进入 `main`；本地与
  远端只保留 `main`，旧修复线和 V4.9 功能分支均已删除且没有遗失独有提交。
- Runtime 是单一 `source_coordinate_photo_geometry` detector。没有旧 Grid detector、
  fallback、双 schema、compatibility shim、旧 import alias 或 review export 旁路。
- 用户提供的 format 是 authority。Full 使用固定张数；partial explicit 严格服从用户
  count；partial auto 输出唯一匹配片夹对该 format 的容量 slots，不推断真实照片张数。
- ScanCanvas 决定片夹、lane、scale 与 capacity；Grid 只拥有 phase、ordinal、blank 与
  interaction。Grid、outer、content bbox 和 corridor 都只是 search proposal，不是照片边。
- Pixel observation 产生 transition、line、support、residual、angle 与 measurement
  uncertainty；format/count/scale/aperture/lane/adjacency 只作 physical constraint 或 named
  inference。Observed 与 inferred provenance 始终分开。
- `FramePhotoGeometry` 是非空照片 source-coordinate 四边与 polygon 的唯一 owner；空容量
  slot 使用 `GridInferredBlankOutputGeometry`。安全输出依次加入 measurement 或 inference
  uncertainty、1 source-pixel interpolation allowance、固定毫米 protection 与 authority
  clipping，不使用跨候选 outward union。
- 新冻结的产品人工成本顺序是：切掉真实内容最严重；过宽非空输出需要逐张人工重裁，
  次之；多余 blank TIFF 可直接删除，成本最低。`approved_auto` 的 V4.9 发布语义必须同时
  包含“零 inward loss”与“非空输出可直接使用”。
- 额外面积可重算不等于输出可用。用户已冻结跨 format 通用的逐边 direct-use budget：
  片条轴 start/end 各为 selected aperture 长轴的 5%，横片条轴 top/bottom 各为短轴的 3%；
  blank geometry 豁免。四边不能互相抵扣，不得用总面积 clamp、历史 box parity 或候选
  union 代替。
- `135-dual` 共用 `135` 比例；120 的 54/56 mm aperture 共用比例并按各自尺寸换算；XPan
  与 120-645 即使没有黄金真实样片也使用通用比例，不建立 denylist。v4.2.8 的 20/10 px
  默认 bleed 与 overlap-risk 50 px 只是历史像素配置，不是新预算 authority。
- 用户已确认 separator/start/end 不应有独立倾角。Top/bottom 的共同方向独占 deskew；
  start/end 必须与其垂直。原始斜边按照片内容最外投影形成正交外包络，黄金人工斜线只作
  containment authority，不要求 runtime 复刻斜率。
- Deskew 只来自 selected observed top/bottom lines 的共同 angle interval。最终 ROI 从原
  TIFF 做一次 inverse-affine sampling，不生成整张旋转 RGB 中间图。
- `CandidateGate` 只记录候选事实；只有 `DecisionGate` 创建 `approved_auto`、
  `needs_review` 与 typed reasons。Review 不产生正式 TIFF 或 provisional product output。

## Current identities

```text
detector kind             = source_coordinate_photo_geometry
measurement receipt      = sha256:a2ad192bcef54c407524108d396f2fae946949d647986e726e3de8117893ab2e
report revision          = source_coordinate_photo_geometry_v1
run manifest             = x5crop_run_manifest_v2
gold cohort              = x5crop_gold_accuracy_cohort_v1
gold result              = x5crop_gold_accuracy_result_v3
gold summary             = x5crop_gold_accuracy_summary_v3
diagnostic cohort        = x5crop_diagnostic_unreviewed_cohort_v1
diagnostic record        = x5crop_diagnostic_record_v1
diagnostic summary       = x5crop_diagnostic_summary_v1
fixed sample profile     = x5crop_fixed_sample_profile_v3
benchmark adapter        = x5crop_benchmark_adapter_result_v1
paired performance       = x5crop_paired_performance_v1
benchmark workload SHA   = 8ebbb0a8213d72fa2f8573c4546babb999b55a87044f25f7379b953508554817
```

黄金 geometry 的唯一 tracked owner 是
`tools/regression/cohorts/gold_accuracy.jsonl`。忽略目录中的旧人工 baseline 只保留为来源
证据，不再被 verifier 或 runtime 消费。

## 已验证检查点

### Current tree 与 contracts

- `python3 -m unittest discover -s tools/tests -p 'test_*.py'`：59/59 通过。
- `python3 -m compileall -q X5_Crop.py x5crop tools`：通过。
- `python3 -m x5crop.configuration.consistency`：13 个 format/mode pairs 通过。
- `python3 -m tools.regression.benchmark_workload --validate`：168 个 tracked tasks 通过，
  workload SHA 如上。
- Pre-push full verification 在 `main` 提交 `f3990e9e` 上通过，并成功推送到
  `origin/main`。同一冻结 checklist 的两轮只读审计均通过。
- Fresh V4.9 package 构建验证通过：10 个 manifest entries、standalone 版本 `4.9`、中文
  UTF-8 路径及 launcher/installer executable bits 正确。该包是验证产物，验证后已删除，
  没有创建 GitHub Release。

### 黄金 accuracy 与 111-source 诊断

- 九张 source-SHA-bound、用户确认 geometry 的黄金样片展开为 14 个场景：14/14 通过。
- 12 个 `must_approve_safe` 场景均为 `approved_auto`，正式写出并复读 TIFF；S098 安全
  通过，但不参与 nominal calibration。
- S055 explicit/auto 两个场景均为 `needs_review`：存在命中黄金的安全 state 和 protection
  后仍不等价的物理竞争 state，正式 TIFF 数为 0。
- 111-source `diagnostic_unreviewed` 得到 111/111 terminal records，工程合同失败 0；现场
  状态为 74 approved、37 review，但 `recognition_accuracy_verdict = not_assessed`。Filename
  `pass/unknown` 与 filename count 没有被消费为 expectation。

### Direct-use 人工冻结

- 临时校准包对 9 张 source-SHA-bound 黄金 TIFF、47 个确认照片框分别生成片条轴与横片条轴
  `0/1/3/5/7%` 对照，共 470 格；源 SHA、全部 21 张 JPG 与比例换算在交付前通过检查。
- 用户于 2026-08-01 明确选择片条轴每边 5%、横片条轴每边 3%，并取消组合复核需求；
  `build/direct-use-calibration-universal-v1/` 随后按用户要求删除。该人工决定而非临时 JPG
  是预算 authority。

### 正式 paired performance

- 固定基线为 tag `v4.2.8` / commit
  `8d14c55d8af5c944a0b78b51df4c4c428e606f07`；V4.9 receipt 对应功能提交
  `7ab4daef95489e9ba2fbd321347270c8a084bd48`。
- 固定 24 个 source、168 个 status-independent I/O tasks、`--jobs 2`，三组顺序为
  `4.2.8→4.9`、`4.9→4.2.8`、`4.2.8→4.9`。
- V4.9 measured median 为 `4.942535770833274 秒/输入`，通过 `<=5.0` 硬门槛；paired
  total wall 的 median relative difference 为 `-32.280782%`，通过 `1%` noise floor。
  这里表示耗时降低约 32.28%，不是吞吐率只增加 32.28%。
- `f3990e9e` 只改 regression/test owner 名称、删除无消费者 helper、同步 CLI 文案与文档，
  没有改变实际 detector 路径。因此上述 receipt 可说明当前 detector 性能；若要把正式
  Release receipt 绑定到最终 HEAD SHA，仍应在发布前重跑 paired benchmark。

## 验证边界与开放风险

- 当前 runtime 只完成了 uncertainty/interpolation/protection 的来源重算、固定保护与
  source/lane clipping。`output_protection` 仍只检查 resolved geometry 是否完整，没有独立
  阻止“内容安全但宽到需要人工重裁”的非空输出。这是新确认的 V4.9 发布 blocker。
- Direct-use budget 的数值已经冻结，但 canonical typed spec、最小正交基准、source-coordinate
  逐边 metric、CandidateGate 事实和黄金 comparator 验收尚未实现。Source/lane clipping 后可按
  实际外扩计费，但 containment 与 authority 必须独立成立。
- 当前 `PhotoBoundaryMeasurementSpec.maximum_search_angle_degrees=4°` 同时允许 start/end
  独立斜线，`test_nonorthogonal_start_end_does_not_widen_shared_deskew` 也保存这一旧合同。
  这与已确认的正交物理模型冲突，并增加无物理收益的 line-family/DP 竞争和纹理误配机会；
  风险方向已确认，但误检率尚未量化。
- Accuracy blocker 只有九张黄金、14 个场景。八张 nominal 可以冻结参数并参与验收；S098
  只作 stress-excluded calibration，但仍必须安全通过。
- 111-source 只证明程序、schema、TIFF、authority 与有界 query/DP/memory 工程合同；没有
  形成人工确认 accuracy 结论，也没有 must-pass status expectation。
- `real_holdout = unavailable`。未覆盖的 XPan、120-645 仅具有 physical-rule 与 synthetic
  contract coverage；不得把这一覆盖缺口变成 runtime denylist 或 review reason。
- `Test/` 是 ignored 的本地 authority 资料库，保留原 TIFF、九张黄金来源证据和
  111-source identity。它不进入源码、Release 或 verifier 的目录布局合同。
- Gold、diagnostic、performance、package 和 Debug Analysis receipts 都是可再生运行产物；
  当前 `build/`、benchmark worktrees、Python cache 与 Finder metadata 已清理。任何
  detector、Gate、schema、cohort owner 或 package-source 变化都会使对应 receipt 失效。

## 精确下一步

- 先为正交 start/end 合同增加 fail-first contracts：当前允许独立斜率的测试必须改为只接受
  top/bottom 决定的正交方向；强倾斜内部纹理不得生成额外 separator class；真实斜边必须按
  start 最小投影/end 最大投影保全黄金 polygon。随后删除 start/end 的独立 angle state，保持
  raw observation、位置 uncertainty、相邻 overlap 与旋转等价的垂直行为。
- 再建立唯一 typed direct-use spec：片条轴 5%、横片条轴 3%，用 selected
  `FrameDesignApertureMm` 和 source axis scale 计算四边实际外扩。预算结果由现有
  `output_protection` 记录，超出任一边时由 DecisionGate review 且正式 TIFF 数为零；不增加
  第三个 Gate。
- 黄金 comparator 必须对 12 个 approved 场景的每个非空输出新增逐边 budget 与正交最外投影
  containment 验收，blank 明确豁免。修复后重跑全部黄金、111-source 工程诊断、paired
  performance、package 与 pre-push full verification。
- 上述合同闭合前不应发布 V4.9，也不应恢复旧 detector、schema、compatibility、样片专用规则
  或大面积 clamp。
- 若未来出现 named physical gap，只增加该 gap 所需的 pixel measurement、physical
  constraint、Gate contract 或 source-SHA-bound 人工真值；修复后重跑全部黄金与相关工程
  cohort，不以 area clamp、filename whitelist 或历史 box parity 替代根因修复。
