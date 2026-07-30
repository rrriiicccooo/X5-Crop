# X5 Crop 更新日志

本文件只记录版本级行为、验证边界与回滚背景。当前架构见 `ARCHITECTURE.md`，用户操作见
`docs/user-guide.zh-CN.md` 与 `docs/user-guide.en.md`。

- 当前开发版本：**V4.9**
- 当前稳定发布：**v4.2.8**

## V4.9 当前开发线

V4.9 是破坏性的 current-only 物理模型重构。旧 runtime/schema/compatibility 不是迁移
目标。

### 2026-07-30：bounded safe-crop Grid 实现计划冻结

这是 docs-only 设计冻结；current review-only runtime、`source_core_grid_authority`
schema 与输出行为均未改变。

- 冻结 format/mode/count authority、lane-local ordinal，以及
  `FrameGridSearchPrior`、`GridPlacementSeed`、separator/one-sided observation、
  `FrameGridProposal`、`FrameSlot`、interaction、safe/protected envelope 的唯一职责。
- 搜索改为固定结构上限：每个 lane/component 最多 6 个 placement seeds；每个
  `count - 1` corridor 最多 2 个 image-observed 加 1 个 model-only candidate；每个 lane
  最多 3 个非支配 proposal。Count 12 时每个 lane/component 最多 198 DP states、558
  transitions。Separator-first 只做按 ordinal difference/pitch interval 的有界查询，不做
  raw band 全配对。
- Anchor `2+ / 1 / 0` 分别使用有限 fit、有限 ordinal assignment 与 model-only proposal；
  expected position 只约束 corridor。没有 separator、齿孔不可见、blank 或 inferred
  geometry 都不是独立 review 原因。
- Partial 不使用固定 offsets；首尾 endpoint 独立竞争。Blank 保留 slot；
  contact/overlap 的 bounded shared interval 并入相邻输出。只有整格/ownership、已知内容
  丢失、错误邻片、authority 或 output geometry 风险才阻断。
- 冻结 output-equivalence 与 outward union：count/order/content ownership/interaction
  相同且 union 不进入错误邻片时，多个 geometry 可合并并自动批准。短轴默认可保留完整
  authoritative lane；缺少短轴照片边不送审。
- 冻结毫米 protection：表值均为每侧值，使用独立 scan-canvas scale interval 的 upper
  endpoint 向上取整；先合并 safe envelope/shared interval，再应用固定 protection。只有
  protection 可在 source/lane 边界饱和，原始 envelope 不得 clamp。
- `CandidateGate` 只保存十一项安全事实；只有 `DecisionGate` 创建 final status 与冻结的
  typed reasons。原子切换时唯一 report revision 将改为
  `bounded_safe_crop_grid`，不保留旧 reader、alias 或双路径。
- 实施顺序冻结为 contracts、八张 nominal 只读 calibration、135/full 与
  120-66/partial 最小纵切、安全交互、原子 runtime/schema 切换，最后运行九张人工证据、
  代表性 cohorts、111 invariant 与固定 24 张真实 TIFF 性能/保真认证。S098 只作 stress。

### 2026-07-30：历史机制回收审查并入新 Grid 计划

这是 docs-only 设计计划更新，current review-only runtime、schema 与输出行为均未改变。

- 只读审查 `v4.2.8`、V3 archive、`X5_Split_v17/v18` 与 source-core 切换前 V4.9。
- 将 expected-position corridors、separator band / edge-pair、learned one-sided edge、
  anchor-derived robust Grid、floating / separator-first placement、format geometry、
  edge-evidence frame fit、blank/contact/overlap、nearby/semantic measurements、
  short-axis/deskew proposal，以及 V4.9 ordered slot / boundary-role / uncertainty / work
  statistics 合同加入新的安全 Grid 计划。
- 回收项必须按 current typed owners 重写。Observed 与 inferred 保持分离；最终输出通过
  `SafeCropEnvelope` 与毫米 protection 吸收有界差异，只有 `DecisionGate` 创建
  `approved_auto` / `needs_review`。
- 明确不恢复自动 format/count、旧 partial offsets、无 corridor 的全轴组合、dense
  graph/sequence solver、fallback/retry、历史 confidence/gate、post-Decision geometry
  polish、pixel bleed、旧 schema/compatibility 或样片规则。
- V3.4.2 local-grid 与 V3.5 semantic hard-gap 的历史 action 已有回归失败，只保留
  proposal/diagnostic measurement 参考；旧 overlap/lucky-risk 也不直接决定 review。
- 下一步先锁定各 format/count 的 placement/candidate/proposal/work 上限、ordered-DP
  assignment、slot ownership 与 safe-envelope equivalence，再获得用户批准后实现最小纵切。

### 2026-07-29：产品目标与自动批准合同纠偏

这是设计合同变更，尚未改变 current review-only runtime。

- 产品成功标准从“唯一证明真实照片边界与独立 Grid phase”改回“在用户提供 format/count
  后，生成足够安全且不切掉真实内容的保守裁切”。向外多保留少量像素可以接受，不追求
  手术刀式边界精度。
- Format/count 是 authoritative runtime input。Separator、content、outer、expected
  position、格式模型与 score 可以参与 bounded proposal、assessment 和 selection；
  observed/inferred provenance 仍必须保留。
- `approved_auto` 表示 protection 后的输出满足安全合同，不表示所有边界均被观测或唯一
  证明。精确 geometry 不唯一但 slot ownership 与安全输出等价时可以自动批准。
- `needs_review` 只用于 protection 无法吸收的实际风险：整格/ordinal 或照片归属歧义、
  count 无法成立、已知内容仍会被切掉、候选会混入错误相邻照片，或越出 source/lane
  authority。
- Partial 可推断 slot placement；blank 保留 slot；contact/overlap 可让相邻输出框重叠并
  重复保留共享像素。
- `CandidateGate` 仍只记录候选与安全事实；只有 `DecisionGate` 创建 final status 与
  reasons。回归验收改以 count、顺序、slot ownership、真实内容 containment、允许的
  outward over-retention 与 TIFF 保真为目标，不要求历史 box parity。
- 下一步先按新宗旨重新审阅此前的 separator-anchor / model Grid 方案；在用户批准
  决策完整设计前不修改 tracked detector，也不原样恢复旧 runtime/schema。

### 2026-07-29：source-core 安全基线原子替换

#### Current runtime 依赖闭合

- Positive-content 严格 4-connectivity 改由 NumPy RLE 与确定性 union-find 实现，不再依赖
  `scipy.ndimage`。Current runtime、CI、macOS/Windows launcher 与 installer 的用户依赖
  统一为 `numpy`、`tifffile`、`imagecodecs` 与 `Pillow`。
- SciPy 与 OpenCV 只保留为未来版本可能评估的能力，不是当前依赖，也没有 optional import、
  fallback 或兼容分支。
- Current-only contract 固定检查 CI、installer、launcher、公共文档与 active source 的依赖
  集合，防止再次出现“本地 Hook 通过、远端 workflow 失败”的漂移。

#### Current-only 残留收口

- 删除不可达的自动批准与 Debug PASS 分支；当前成功处理只有 `needs_review`。
- 删除永远返回空列表的 frame-export runtime 包装；独立 ROI/TIFF foundation 保持不变。
- `SourceContentComponent` 不再重复保存与 `positive_cells` 相同的 channel cell 数；分 channel
  总量仍由唯一 measurement statistics owner 保存。
- 删除已经不存在的 candidate build 目录在 `.gitignore` 中的过期例外。

#### 能力收紧

- 当前运行流固定为：

  ```text
  TIFF
  → base gray / statistics
  → scan-canvas/lane authority
  → independent axis scale intervals
  → immutable positive content
  → FrameGridEvidence
  → CandidateGate
  → DecisionGate
  → review/report
  ```

- 当前没有获批的独立 Grid phase authority。所有需要 frame 定位的输入均为
  `needs_review / frame_grid_authority_unavailable`，frame boxes 与 TIFF outputs 为空。
- Photo containment 固定为
  `NOT_APPLICABLE_FRAME_GRID_UNAVAILABLE`；Visual deskew 固定为
  `NOT_APPLICABLE_CORE_UNAVAILABLE`。它们不重复制造 final reason。
- 这不是 fallback。Separator、photo edge、outer、content 与设计 width 都无权补出
  Grid phase；runtime 不保留休眠 branch、feature flag 或 baseline/manual phase 入口。
- 当前没有组合搜索，因此不引入 `PhysicalAuditBudget`。Content pixels、runs、components、
  wall time 与临时内存只作为确定性 measurement work 统计。

#### Source core

- `FrameDesignApertureMm` 保存已批准的离散设计 component：
  135/dual `36×24`、half `18×24`、XPan `65×24`、120-645 `42×54/56`、
  120-66 `54×54 / 56×56`、120-67 `70×54/56 mm`。不同 component 不取 hull。
- Scan canvas long/short px/mm 分别计算，在没有额外 measurement uncertainty 时为 point
  interval；两轴互不扩宽，TIFF DPI/PPI 不参与检测。
- `SourceStripValidationDomain` 只来自完整 scan canvas/lane 与 source extent，不接受
  holder、photo edge、separator、Grid、content 或 deskew 缩窄。
- Positive content 明确拆为：

  ```text
  intensity = abs(I - five_point_local_mean(I)) / 255
  texture   = (abs(dx) + abs(dy)) / 510
  positive  = intensity_supported AND texture_supported
  ```

  两个 channel 分别冻结 adaptive threshold；严格 4-connectivity 与 immutable compact
  RLE 保存组件、完整 footprint、censored 状态和 provenance。
- CandidateGate 只检查 source-core；DecisionGate 独占 final status/reasons。
- Runtime report 唯一 revision 改为 `source_core_grid_authority`。没有旧 reader、alias、
  shim、adapter 或 ignored field。`core_facts_sha256` 不包含 measurement wall time。

#### 输出与接口

- 原子删除 `PhotoEdge*`、ridge graph、fragment、scheduler、frame-sequence
  solver/consensus/assignment、旧 separator/profile/score/rank/Top-K、旧 transform
  evidence、rotated gray、shared short axis 与 holder-sequence 链。
- 删除 pixel bleed 整链：`--bleed`、`--bleed-x`、`--bleed-y`、
  `AxisBleedParameters`、`FrameBleedPlan` 及 report/config 字段；不保留 deprecated 参数。
- 删除已经没有 current owner 的 `--export-review` 与 `--dry-run`。当前所有输出本来就是
  review/report 流，保留无效开关会形成兼容假象。
- 格式级毫米 protection authority 成为唯一 owner，但没有 frame geometry 时
  `applied=false`，也没有用户 override。
- Inverse affine、non-clamping half-open mapping、共享 bilinear sampler 与 TIFF ROI
  writer 作为独立 foundation 保留。Contracts 继续验证 identity 精确切片、ROI/reference
  像素一致以及 dtype、axes、ICC、resolution、metadata、NONE/LZW compression 保真。
- Current development docs 明确只生成 review/report。稳定公开 Release 仍为 v4.2.8。
- Standalone `X5_Crop.py` 继续由唯一 release builder 从 modular tree 生成；启动器和
  installer 只检查当前四项 runtime dependency。

#### 原型证据边界

重启前证据保存在 ignored 目录
`Test/local_audit_evidence/2026-07-29-source-core-cutover/`，包含 SHA-256 manifest 与完整
dirty patch。它不会进入 Git 或 Release。

这些实验分别否定了特定表示，不能扩大为“原始 TIFF 没有 separator 信号”：

- exact top × bottom photo-edge 在八张 nominal 上不能稳定产生唯一 pair；
- 独立 leading × trailing 笛卡尔积覆盖不完整且组合超预算；
- 原子暗带与“找到全部 separator”产生大量同等成立 content bands；
- historical separator-width conservation 缺少独立 sequence extent，实际没有增加
  topology 判别力；
- row-section association、streaming connected mask、fragment/K-message 与 origin
  proposal 表示分别在覆盖、预算或性能上失败；
- confirmed-line signal matrix 否定的是
  `base_gray_u8 + current local-noise/integration` measurement 合同，不证明原始 TIFF
  缺少物理信号。

因此 current tree 不再临时追加 separator 补丁，也不借旧 detector 维持自动输出。未来
只有新的、决策完整且有界审计的 Grid proposal 与 safe crop envelope flow 才能重新打开
frame finalization；它不需要唯一证明真实 Grid phase。

#### 验证与性能边界

- Focused contracts 覆盖 format/scales、unique domain、independent content fields、
  4-connectivity/censoring、Grid unavailable、两级 Gate、current schema、旧参数拒绝与
  ROI/TIFF foundation。
- Named current-flow audit 覆盖 S027、S035、S051、S055、S062、S091、S094、S109 与
  S098；预期均为 review、无 frame output。
- 固定 24 张 detector-only 诊断使用 `--jobs 2`，cold 单列，三次中位数必须严格小于
  `5.0 秒/张`才说明保留未来生产余量；这不是正式性能 PASS。
- 移除 SciPy 后，NumPy RLE/union-find 在 600 组独立 oracle mask 与 111 张 current
  样片上保持严格 4-connectivity/content geometry 一致；固定 24 张三轮中位数为
  `2.216 秒/张`（`--jobs 2`）。
- 当前没有 auto-export capability，真实 24 张 TIFF 写出认证必须为 `not_certified`。
  Bounded Grid proposal 与 safe crop envelope 恢复输出后，才要求三次真实写出并复读的
  中位数 `<=5.0 秒/张`。
- 111 张只作一次发布前 source-core invariant 审计。

### 2026-07-26：人工 baseline 与仓库 owner 收束

- 九张黄金样片由用户确认并绑定 source/annotation/proposal/review hash。八张属于
  `nominal_calibration`；S098 只作为 `irregular_geometry_stress`。
- 人工 baseline 权限只来自绑定 source SHA 的用户直接确认或独立校准的外部测量。
  模型视觉、OpenCV、SciPy、X5 Crop、生成 JPG 与算法一致都只能产生非权威 proposal。
- 内部文档改为中文唯一 owner，公共中英文手册与快速启动分别维护。

## v4.2.8 稳定发布

v4.2.8 仍是面向普通用户的稳定 GitHub Release；V4.9 source-core 开发基线尚未替代它。

## 发布与回滚

- 发布包内容由 `tools/release/manifest.py` 独占，通过
  `python3 -m tools.release.build --version <version>` 构建。
- V4.9 回滚必须整体恢复匹配的物理模型、configuration、workspace、schema、tests 与 docs；
  不得把旧 detector/schema 与 current source-core 混用。
- 历史源码只从 Git history 与 release tags 恢复，不在 current tree 建立 archive。
