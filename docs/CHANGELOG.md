# X5 Crop 更新日志

本文件只记录版本级行为、验证边界与回滚背景。当前运行合同见
[ARCHITECTURE.md](ARCHITECTURE.md)，用户操作见
[中文用户手册](user-guide.zh-CN.md)与[英文用户手册](user-guide.en.md)。

- 当前开发版本：**V4.9**
- 当前稳定发布：**v4.2.8**

## V4.9 当前开发线

V4.9 是破坏性的 current-only 物理模型重构。旧 runtime、schema、reason、cache、
compatibility 与历史 box parity 均不是迁移目标。

### 2026-07-30：冻结 partial auto 的容量输出目标（尚未实现）

- 用户确认额外空白输出与完全空片的空白输出均可接受；产品风险改为非对称：少输出可能
  漏掉真实照片，容量范围内多输出只增加可接受的 blank slot。
- 下一原子切换将把 partial `auto` 从“在有限 count 集合中推断真实张数”改为“输出唯一
  匹配片夹的全部有效 slots”。`fixed_full` 与 authoritative `explicit` 不变；auto 的
  canonical 身份改为 `output_slot_count`，不再声称是真实照片数。
- `main@7478ca09` 的只读复核显示：14/14 黄金场景通过，111 条 coverage 中 110 条已批准；
  问题不是 review 过多，而是 41 条 pass partial 中有 17 条在少于人工 count annotation
  时仍得到批准。S067 作为非 baseline 诊断可直接复现 auto 输出 1 个中间 ROI，而
  explicit 3 输出三张；这证明现有批准语义可能保守错方向。
- 使用 current 单-count 路径请求这些样片的格式最大容量（与其匹配片夹容量相同）的只读
  模拟覆盖全部 51 条 partial，51/51 均得到输出且没有低于 annotation。五张用户确认
  geometry 的 partial 黄金样片全部完成
  source-order containment；S109 的七张确认照片映射到十二个 holder slots 的第 6–12 位，
  证明前导 blank 可以表达真实 partial placement。
- 该策略不采用新的跨 count coverage 层。实现时删除跨 count dominance、count competition
  与对应 schema/reason/contracts，只保留单一容量 count 内的 Grid、ownership、
  containment、protection 和两级 Gate。
- 固定 24 张性能 cohort 按容量输出时，静态 frame 数估计由 139 增至 168（增加 29，
  约 21%）。同时 half auto 每个 lane/component 的搜索结构上限可从 1188/3168 降为
  count 12 的 198/558 states/transitions；最终取舍必须以真实 TIFF 写出/复读性能为准。
- 本条只冻结下一实现边界，不改变当前 runtime、公共用户手册或稳定 Release。原子切换、
  current schema、验收和性能全部闭合后，才更新用户可见行为说明。

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
