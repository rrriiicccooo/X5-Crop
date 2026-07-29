# X5 Crop 更新日志

本文件只记录版本级行为、验证边界与回滚背景。当前架构见 `ARCHITECTURE.md`，用户操作见
`docs/user-guide.zh-CN.md` 与 `docs/user-guide.en.md`。

- 当前开发版本：**V4.9**
- 当前稳定发布：**v4.2.8**

## V4.9 当前开发线

V4.9 是破坏性的 current-only 物理模型重构。旧 runtime/schema/compatibility 不是迁移
目标。

### 2026-07-29：source-core 安全基线原子替换

#### CI 依赖闭合

- GitHub `Verify` 现在与 macOS/Windows installer 一致安装
  `numpy`、`scipy`、`tifffile`、`imagecodecs` 与 `Pillow`，避免干净 runner 在导入
  source-core 时缺少 `scipy.ndimage`。
- Current-only contract 固定检查 CI 与两套 installer 的 runtime package 集合，防止后续
  依赖漂移再次造成“本地 Hook 通过、远端 workflow 失败”。

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
- Standalone `X5_Crop.py` 继续由唯一 release builder 从 modular tree 生成；SciPy 加入
  launcher/installer 的明确 runtime dependency。

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
只有新的、独立批准且完整审计的 Grid phase authority 才能重新打开 frame finalization。

#### 验证与性能边界

- Focused contracts 覆盖 format/scales、unique domain、independent content fields、
  4-connectivity/censoring、Grid unavailable、两级 Gate、current schema、旧参数拒绝与
  ROI/TIFF foundation。
- Named current-flow audit 覆盖 S027、S035、S051、S055、S062、S091、S094、S109 与
  S098；预期均为 review、无 frame output。
- 固定 24 张 detector-only 诊断使用 `--jobs 2`，cold 单列，三次中位数必须严格小于
  `5.0 秒/张`才说明保留未来生产余量；这不是正式性能 PASS。
- 当前没有 auto-export capability，真实 24 张 TIFF 写出认证必须为 `not_certified`。
  独立 Grid authority 恢复输出后，才要求三次真实写出并复读的中位数
  `<=5.0 秒/张`。
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
