# X5 Crop 更新日志

本文件只记录版本级行为、验证边界与回滚背景。当前运行合同见
[ARCHITECTURE.md](ARCHITECTURE.md)，用户操作见
[中文用户手册](user-guide.zh-CN.md)与[英文用户手册](user-guide.en.md)。

- 当前开发版本：**V4.9**
- 当前稳定发布：**v4.2.8**

## V4.9 当前开发线

V4.9 是破坏性的 current-only 物理模型重构。旧 runtime、schema、reason、cache、
compatibility 与历史 box parity 均不是迁移目标。

### 2026-07-31：source-coordinate 照片几何重建

- 原子替换旧 `bounded Grid` detector：Grid 现在只拥有 capacity、phase、ordinal、blank
  与 interaction；`FramePhotoGeometry` 独占非空照片的 source-coordinate
  top/bottom/start/end、polygon、逐边 provenance 与 uncertainty。
- 新增 streaming `PhotoBoundaryMeasurementField/Query/Set`、完整 coverage receipt、
  `PhotoEdgeSearchCorridor` 与 `SequenceAnchorDiscoveryDomain`。所有 query 预登记，Grid、
  content 与 outer 只改变查询域或执行顺序，不能成为照片边或 measurement uncertainty。
- Format aperture 使用 typed `±0.5 mm` tolerance；full/explicit 固定 N，partial auto
  固定片夹容量。长轴序列可以由任意 observed internal/trailing anchor 向前或向后求解，
  不再依赖 outer 找到第一张。无绝对照片 anchor 时不创建照片 geometry。
- Top/bottom 使用完整窄 corridor/halo、二维 transitions、line families 与成对尺寸/角度/
  content/scanner-border 验证；允许 observed opposite edge 加 rotation/scale/aperture
  interval 的 named inference，但两侧不可见时不从理论 corridor 造边。
- 候选在组合成完整 `FrameGeometryState` 后去重和 dominance；超过两个 observed
  non-dominated states 时在截断前 unresolved。Lane-local DP 保持 `K≤3` 与
  `O(N×K²)`；auto 不枚举 occupancy。
- Empty capacity slot 改用独立 `GridInferredBlankOutputGeometry`。照片 translation 与
  Grid slot translation 分开；只有所有 placement 的 protected/clipped half-open
  footprint 等价时，blank-only 输出才能批准。
- Deskew authority 只来自 selected observed top/bottom lines 的共同 angle interval；
  identity 必须由零角度证据支持，非零 rotation 直接从原 TIFF 做一次 inverse-affine ROI
  sampling。删除 identity-only、整图旋转中间图、固定 uncertainty、nearest-line 与跨候选
  outward union。
- Current report revision 更新为 `source_coordinate_photo_geometry_v1`；Debug Analysis
  固定 source、pixel measurement、selected source geometry 与 protected output 四层。
  Raw transitions 与 content components/row runs 只保存 coverage、数量、canonical
  row-run digest 与 component derivation，不再逐条膨胀 report。Review 没有正式 TIFF
  或 provisional export 路径。
- 黄金 authority 等值迁移到 tracked
  `tools/regression/cohorts/gold_accuracy.jsonl`；旧 ignored baseline 只保留为人工确认
  来源证据，不再被 verifier 消费。九张黄金、14 场景是唯一 accuracy blocker；S098
  必须安全通过但不参与 nominal calibration。
- 111-source 改为 `diagnostic_unreviewed`：filename `pass/unknown` 与 filename count
  不再产生 expectation，只阻断 crash、schema/TIFF/authority 和有界资源等工程合同；
  单输入临时内存按 `10 × source pixels + 32 MiB` 的线性上界验收。
- 性能改为 status-independent paired total wall：固定 V4.2.8 commit
  `8d14c55d8af5c944a0b78b51df4c4c428e606f07`、24 个 source、168 个冻结 I/O tasks、
  `--jobs 2`，要求 V4.9 median `<=5.0 秒/输入` 且在 MAD 噪声之外更快。
- Source content ownership 改为完整 source domain 的确定性 streaming 测量；不降低空间
  分辨率，也不再同时保存整幅多套 float field。
- 本节整体取代下方 2026-07-30 的 Grid schema、111 blocking expectation 与旧 performance
  方法；下方条目仅保留演进和回滚背景。

### 2026-07-30：移除 `--debug` 并恢复 Debug Analysis 三联图

- 删除轻量 `--debug` CLI、`RuntimeOptions`/`RunConfig` 字段、bootstrap 传递、
  `_debug/` 写出路径和两种 debug 输出分发 wrapper；不保留 alias、deprecated flag 或
  compatibility branch。`--debug-analysis`、`--diagnostics` 与 `--debug-errors` 保持。
- Debug Analysis 重新固定为 `Original gray context`、`Frame outputs`、
  `Separator evidence` 三联图和一个总状态栏。它只使用 canonical `gray_work`，不增加
  局部放大、第四面板或 Gate 矩阵。
- Approved 只绘制 final protected boxes；F1–F12 按 global ordinal 使用固定唯一颜色、
  0.26 半透明填充和 2 px 同色边框。Review 不伪造 final output，只把已有 selected
  proposal 画为低透明度虚线 provisional envelopes，并标记 `NOT EXPORTABLE`。
- Separator 面板保留全部 raw observations；selected edge-pair、one-sided 和 model-only
  Grid 分别使用红色实线、橙色实线和 cyan 虚线，取消 256 条展示截断。横向 work view
  纵向堆叠，portrait view 横向排列，间距 12 px、标题栏 34 px、JPEG quality 92。
- Current-only contracts 覆盖 CLI/runtime surface、普通与 diagnostics 写出、三面板布局、
  final/provisional 边界、F1–F12 跨 lane 映射、overlap、portrait 与超过 256 条 raw
  separator 时的 selected observation 可见性。Detection、report schema、DecisionGate、
  final boxes、TIFF output、版本号与 release manifest 均未改变；本次不构建发布包。
- 冻结变更前后 5 组真实 current report 后，`grid_selection`、`candidate_gate`、
  `decision` 与 `output.finalization` 对照均为零差异；人工检查 `135/full`、
  `135/partial`、`half/full`、`120-66/partial auto`、`120-67/full` 三联图，未见原图
  染色、frame ordinal 混乱、selected separator 遮蔽或真实内容 inward loss。

### 2026-07-30：partial auto 容量 slots 原子切换

- Partial `auto` 现在只使用唯一匹配 `ScanCanvasEvidence` 中对应
  `ScanCanvasFormatFit.maximum_frame_count`，输出该片夹对当前 format 的全部有效 slots。
  `fixed_full` 与 authoritative `explicit` 保持精确；auto 不再推断或声明真实照片张数。
- 新增唯一 `ResolvedOutputSlots(lane_output_slot_counts)`。总 slot 数只由 canonical lane
  counts 求和；candidate、final detection、report、manifest 与输出文件共同引用或派生
  同一 resolution。`135-dual` 固定为 `(6, 6)`，按 lane 0 后 lane 1 输出。
- 每个 lane 只搜索一个 resolved slot count。Score、residual 与 tie-break 只负责构建顺序
  和诊断展示；只有 output-equivalent proposals 可以 outward union。两个非等价
  placement、ordinal 或 ownership classes 不会被排序选出赢家。
- `GridOmissionSummary` 对 seed、corridor 和 DP frontier 的每个截断保存确定性 scope、
  omitted alternative 与 absorbing class identities。只有全部 omitted outcomes 已证明
  等价并进入 outward union 才不阻断；否则 `grid_search_coverage` 阻止输出。
- `CandidateGate` 的第四项改为 `output_slot_count`。容量已解析但无法形成全部 slots 时，
  fixed/explicit 使用 `requested_count_unfulfilled`，auto 使用
  `capacity_output_slot_count_unfulfilled`。只有 DecisionGate 创建 final status/reasons。
- Grid algorithm 更新为 `bounded_ordered_capacity_grid_v5`；calibration receipt 更新为
  `x5crop_grid_calibration_receipt_v2`，保留原数值 prior 与
  `user_confirmed_geometry` provenance。Current schemas 更新为 report
  `bounded_safe_crop_capacity_grid`、run manifest `x5crop_run_manifest_v2`、fixed profile
  `x5crop_fixed_sample_profile_v2` 与 performance `x5crop_production_performance_v4`。
- 真实验收通过 14/14 黄金场景；111/111 blocking audit 通过，其中 88/88 `pass_*` 与
  41/41 pass partial 全部 `approved_auto` 并精确输出匹配片夹容量。23 条 `unknown_*`
  中 22 条批准，S111 因具体 output-slot/protection Gate 阻断进入 review。
- 固定 S062 profiling 输出 profile `120_wide_224_5`、lane counts `(3,)`；detection
  `2.581 秒`，所有 36 个 omitted alternatives 均被等价 class 吸收。
- 正式 24 张、`--jobs 2` 四轮性能每轮写出并复读 168 个 TIFF；九个 partial 输入比
  filename annotation 多 25 个 slots。三轮 measured 中位数为 `2.499 秒/输入`，通过
  `<= 5.0 秒/张` 合同。
- 本次不新增 GitHub Release。`real_holdout = unavailable`；XPan、120-645 等无真实样片
  cell 继续只由 physical-rule synthetic contracts 覆盖。

### 2026-07-30：普通并发上限开放到 3

- 将普通入口的默认值与上限拆分：默认保持 `--jobs 2`，用户可显式请求最多 3 个
  worker；诊断上限保持 4。
- 四 worker 不开放给普通运行。真实 TIFF 对照显示三 worker 在输入足够时有吞吐收益，
  但单任务耗时和峰值内存压力也会上升；四 worker 对常见机器不是稳妥的常规上限。
- 正式 24 张性能认证仍固定 `--jobs 2`，本次不改变 `<= 5.0 秒/张` 合同。
- Current-only contract 固定默认 2、普通上限 3、诊断上限 4 及 runtime boundary 的
  实际归约。

### 2026-07-30：仓库结构与本地工作区收敛

- 关闭 sparse checkout，将 `LICENSE` 与其它受跟踪文件全部保存在本地。
- 除根目录必需的 `README.md`、`AGENTS.md` 与 `LICENSE` 外，实质性文档统一收敛到
  `docs/`；项目记忆重写为短 current checkpoint，不再保存已执行计划全文。
- Installer 模板从根 `install/` 移至 `tools/install/`。Release manifest 仍将它们映射到
  用户 ZIP 的 `install/`，并新增根 `LICENSE`。
- 删除未进入发布包且整份复制主 launcher 的 macOS diagnostics launcher；诊断继续由
  canonical CLI `--diagnostics` 提供。
- 删除会操作共享 Python packages 的 uninstall wrappers。X5 Crop 是便携目录，移除程序只
  需删除目录；依赖可能被其它程序共用，不再提供项目级批量卸载动作。
- 删除本地 `dist/`、Python cache 与已被 current runtime 取代的 ignored source-core
  prototype/cutover 生成物；保留原 TIFF、111-source manifest 与九张黄金样片证据。
- Current-only contract 新增文档、installer、release manifest 与根目录布局检查。

### 2026-07-30：bounded safe-crop runtime 原子切换

- Runtime 原子切换为 `bounded_safe_crop_grid`。Full 使用 `fixed_full`；partial 支持
  authoritative `explicit` 与 bounded `auto` count。没有 feature flag、旧 reader、
  fallback 或双 schema。
- `ScanCanvasEvidence` 独占 scale；source core 只保存 lane/domain/positive-content
  facts；独立 separator owner 建立 long-axis field、bands、edge-pairs 与 learned
  one-sided observations。Tracked calibration receipt 只校准 prior，不把确认的照片边
  写成 runtime observation。
- Grid flow 实现 bounded placement、local corridors、ordered DP、逐 count dominance、
  lane-global selection、`FrameSlot`、shared interaction、outward safe envelope 与固定
  毫米 protection。结构上限为 `P_MAX=6`、`O_MAX=2`、`K_MAX=3`、`G_MAX=3`；count 12
  的每个 lane/component 上限为 198 states/558 transitions，auto 1..12 为 1188/3168。
- Hard rejection 只来自容量、非法 geometry、未保护 geometry 越出 authority，或已知内容
  无法有界归属/包含。Score、safe-envelope 大小、separator 缺失、blank、model-only 与
  protection saturation 不能制造 hard rejection。
- 跨 count selection 使用 typed dominance；浮点 equality interval、count 1 的
  `NOT_APPLICABLE` corridor、output-equivalent outward union 与 search-incomplete
  阻断语义均由 current contracts 固定。
- CandidateGate 固定为十项安全事实；DecisionGate 独占 `approved_auto`、
  `needs_review` 与 typed reasons。DecisionGate 后 count、transform 与 boxes 不可变。
- Approved runtime 对每个 ROI 只采样原图一次；写出后复读验证 pixels、dtype、
  axes/channels、ICC、resolution、metadata 与 NONE/LZW 无损压缩。读取、写出或复读错误
  保持独立 `FailedInput`，不转换成 review。
- Report revision 更新为 `bounded_safe_crop_grid`；performance schema 更新为
  `x5crop_production_performance_v3`。

### 2026-07-30：验收与性能边界

- 九张 source-SHA-bound、用户确认 geometry 的黄金样片展开为 14 个
  fixed/explicit/auto 场景。Containment 只检查 inverse-transform 后的 source footprint
  是否完整包含 confirmed polygon；允许更大、重叠或含邻片像素。
- 111 条 manifest 只作非阻断 coverage audit；重复 SHA 单列，record 数不冒充独立样片数。
  `real_holdout = unavailable`；XPan、120-645 等缺口标记
  `real_sample_coverage = unavailable`。
- 正式性能固定 24 张、`--jobs 2`，在同一空 root 下执行 `cold` 与
  `measured-1/2/3`。四次均写出并复读 frame TIFF，认证只计算三次 measured 中位数，
  合同为 `<= 5.0 秒/张`。
- `tools/verify` 仍是唯一 tracked verifier；pre-commit 执行 staged hygiene，pre-push
  执行唯一最终 full validation。正常 push 前不手工重复 full。

### 2026-07-29：source-core 安全基线（已被当前 runtime 取代）

- 删除旧 PhotoEdge、ridge/fragment/sequence solver、pixel bleed、fallback/retry、
  compatibility shim、旧 report/schema/reason 与不可达 output wrapper。
- Positive-content 改为 NumPy RLE 与 deterministic union-find 的 strict
  4-connectivity；runtime dependency 收敛为 `numpy`、`tifffile`、`imagecodecs` 与
  `Pillow`。
- 建立 format、scan-canvas、axis scale、source domain、positive content、Gate、
  inverse-affine ROI 与 TIFF fidelity 的 current owners。
- 当时的 review-only `source_core_grid_authority` 只是原子切换检查点，已由
  `bounded_safe_crop_grid` 整体取代；不得恢复其 reader、status 或 reason。

### 2026-07-26：人工 baseline 与文档 owner 收束

- 九张黄金样片由用户确认并绑定 source/annotation/proposal/review hashes；八张用于
  nominal calibration，S098 只用于 stress。
- Baseline authority 只来自绑定 source SHA 的用户明确确认或独立外部测量。模型视觉、
  OpenCV、SciPy、X5 Crop、生成 JPG 与算法一致只能产生非权威 proposal。
- 内部文档采用中文；公共用户手册与快速启动按中英文分别维护。

## v4.2.8 稳定发布

`v4.2.8` 仍是当前稳定 GitHub Release。V4.9 未创建新的 Release，也不改变既有发布资产。

## 发布与回滚

- 发布包内容由 `tools/release/manifest.py` 独占，通过
  `python3 -m tools.release.build --version <version>` 构建。
- Package 构建后若 tracked tree 变化，必须重新构建检查。
- V4.9 回滚必须整体恢复匹配的物理模型、configuration、workspace、schema、tests 与
  docs；不得把旧 detector/schema 与 current runtime 混用。
- 历史源码只从 Git history 与 release tags 恢复，不在 current tree 建立 archive。
