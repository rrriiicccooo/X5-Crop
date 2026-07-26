# X5 Crop 更新日志

本文件只记录版本级行为、验证边界与回滚背景。当前架构见 `ARCHITECTURE.md`，用户操作见
`docs/user-guide.zh-CN.md` 与 `docs/user-guide.en.md`。

- 当前开发版本：**V4.9**
- 当前稳定发布：**v4.2.8**

## V4.9 当前开发线

V4.9 是 current-only 的物理模型与源码重构。历史 PASS/REVIEW、report schema、人工标签
和裁切 geometry 不是兼容目标。

### 2026-07-26：S027 边缘表示与搜索完整性

- Photo-edge observation 改为 channel-local uncertainty：intensity、texture、gradient
  各自用本 channel 的 response 与 local noise 形成连续 support interval；任一 channel
  可独立贡献，多尺度合并要求所有实际参加的 support 具有共同交集，不再用传递重叠连接
  两个 transition。
- `PhotoEdgeRidgeGraph` 成为 observation 与 ridge identity 的唯一 owner。Node 唯一拥有
  observation，edge 只表示相邻 anchor 的直接连续证据；`PhotoEdgeFragment` 只引用完整
  source-to-sink node-ID path。没有直接证据不建 gap edge，geometry 按 observation ID
  去重，也不能从单链曲线截取局部直线。
- Line feasible region 保留逐 polygon 的精确交集与全部不相连 slope/θ 分量，不再用全局
  slope 外包填回中间禁区。只有既有 `_POLYGON_EPSILON` 可合并数值接触的分量。
- `GeometryWorkBudget` 继续独占可变计数：consensus state 与实际 cell evaluation 都按
  整个求解累计，pending 和预约不扣费。Scheduler 使用固定完整二叉树工作量上界和稳定
  顺序，先完成窄候选；统计只在结束时生成不可变快照。任何 path、hypothesis、region 或
  consensus 分支未覆盖，runtime 都返回 `unavailable`、无 selection、无 finalization。
  Path discovery 已确定不完整时不再继续构造无权采用的 polygon 或局部 witness。
- 固定画布与 image-only lane 共用 graph、scheduler、budget owner 和统计语义；水平与垂直
  使用同一 canonical observer/geometry 流。旧 observations-owning fragment、aggregate
  slope interval、逐 hypothesis 重置预算和相关兼容入口已删除。
- 黄金比较器仍是 runtime 外部只读工具。正式 geometry 才记录 `compared` 并输出逐边角度、
  signed normal distance、危险向外越界、向内内容损失、containment、transform 与 final
  boxes；无正式 geometry 记录 `production_geometry_unavailable` 并保持 `needs_review`。
  `1e-9` 只作数值零判断，本轮不新增方向性 pass threshold，也不自动声明
  `resolved-safe`。
- 验证范围固定为新增表示/预算/调度/旋转与 dual-lane contracts、八张 nominal cohort、
  额外 `half/full`、`S098` stress、current-schema comparison 与 Debug Analysis。`S098`
  不作为 nominal 门槛；S027 的方向性容差校准与最终安全批准仍属于后续独立任务。
- 同配置 S027 修改前 wall time 中位数为 36.03 秒；修复后 warm-up 加三次测量为
  40.49 / 40.70 / 41.06 秒，中位数 40.70 秒、范围 0.57 秒。新增成本来自各 channel
  正确归属的 local noise，不作为物理安全阈值。内部审计记录 118,234 nodes、225,900
  direct edges、8,937 components、85,727 junction nodes、0 个重复 observation owner；
  path discovery 不完整时累计执行 0 cells、注册 0 consensus states，并保持 unavailable。
- 八张 nominal 的外部比较结果均为 `production_geometry_unavailable` / `needs_review`；
  `S051`、`S055`、`S109` 的 count 仍分别为 `5/3`、`5/4`、`11/7`，其余五张 count
  相符但没有正式 geometry。额外 `half/full` 与 `S098` 均无崩溃、无 finalization。
  Debug Analysis 显示 retained fragments 为零，没有可供物理批准的最终边缘。
- CLI、用户配置、production report schema、人工 baseline schema 与公共用户文档不变。

### 2026-07-26：黄金基线、文档与仓库收束

- 九张黄金样片均已由用户确认，形成绑定原图、标注副本、proposal snapshot 与复核 JPG
  hash 的本地 baseline。八张属于 `nominal_calibration`；非矩形、片距不稳的 `S098`
  作为 `irregular_geometry_stress` 保留，但不参与正常容差估计。Production detector
  阈值仍未据此调整。
- `S055` 的正确帧数为四。红线转换器会拒绝“声明帧数少于强短边证据”的输入，不能排序后
  静默丢弃人工笔迹。
- 人工 baseline 权限只来自绑定 source SHA 的用户直接标注与明确 JPG 确认，或独立校准的
  外部测量。模型视觉、OpenCV、SciPy、X5 Crop、生成 JPG 与算法一致只能产生非权威
  proposal。
- 校准目标采用“共享照片边缘 → deskew/共享短轴 → 成对长轴边缘 → 安全矩形 → 独立
  bleed”。验收使用黄金集校准的方向性容差，不追求数学 `0 px`；危险向外越界不得通过，
  bleed 不能掩盖错误基础几何。
- 增加只读黄金基线比较器：只消费 current-schema report 与 user-confirmed baseline，
  将无 bleed 的 production envelope 通过报告中的同一 affine 变换反算回原 TIFF，
  分别记录逐边 signed normal distance、角度、危险向外越界、向内内容损失与 containment；
  没有 final geometry 时保留 `production_geometry_unavailable`，不得拿 provisional
  candidate 冒充输出。
- 八张 `nominal_calibration` 的现场 diagnostics 均为
  `photo_edge_pair_unavailable`，因此尚无 final geometry 可做逐边容差统计；其中
  `S051`、`S055`、`S109` 的 auto count 分别为 `5/5/11`，与确认的 `3/4/7` 不一致。
  这说明第一个 production gap 位于 photo-edge pair resolution，而不是方向性容差过严。
- 删除 641 个与 Git history 重复的 tracked source snapshot；历史版本由 Git history 与
  release tags 恢复，current tree 不再维护 `archive/`。
- 测试审计未发现重复 test body、空 test module、未使用 public support owner 或无静态
  owner 的 active Python module，因此保留全部 current contracts。
- 文档改为中文内部真相源与独立中英文公共发布文档。根 `README.md` 只保留精简双语入口；
  发布包改为 `README_中文.txt`、`README_English.txt`、`快速启动.txt` 与
  `Quick_Start.txt`，不再包含逐段中英混排文档或旧文件名。
- `LICENSE` 保留在 GitHub，本地 sparse checkout 不保存。

### 当前累计行为

- `FramePhysicalSpec` 只保存照片尺寸；`ScanCanvasPhysicalSpec` 只保存片夹扫描画布。
  TIFF DPI/PPI 仅作 I/O metadata。
- 已知单条画布由 source pixel aspect 唯一匹配并生成 `CanvasPixelScale`；无匹配或竞争
  profile 保持 typed unresolved。`135-dual` 不虚构固定画布。
- 分帧前从任意清晰区域形成与材料和极性无关的 photo-edge observation。连续 ridge
  成为不可拆 fragment；法向联合区域同时约束 top、bottom、照片高度、中心、
  containment 与完整 `FrameSizeMm`。
- `PhotoEdgePairEvidence` 是唯一边缘身份真相。Deskew、mapped pair、
  `SharedShortAxisPlan` 与 frame sequence 只消费同一 selected pair；旋转后不重新测量
  短轴。
- Pair identity、transform precision 与全 workspace shared-axis safety 独立判断。
  `CandidateGate` 判断候选，`DecisionGate` 独占最终 PASS/REVIEW。
- 当前 report revision 为 `cross_region_photo_edge_geometry`。Report 与 Debug 只读
  typed evidence，不保存 dense response、不重算 geometry，也不作为 detection cache。
- `tools/` 的 current owner 只有 `verify`、`git/`、`release/`、
  `regression/compare.py`、`regression/golden_baseline.py` 与 `tests/`；退役
  manual-reference regression chain 不再存在。

## 验证边界

- `tools/verify` 是唯一机械验证入口；Hook 与 CI 只调用它。
- Unit/contract、compile、configuration 与 release-package 检查只能证明结构一致性，
  不能证明真实照片边缘已经达到 production accuracy。
- 本地已有九条 user-confirmed crop baseline。八张 nominal 样片已完成 current-schema
  只读审计，但因 production 均未形成 final geometry，尚不能完成逐边方向性误差统计或
  阈值校准。

## v4.2.8 稳定发布

v4.2.8 仍是面向普通用户的稳定 GitHub Release；V4.9 尚未替代它。

## 发布与回滚

- 发布包内容由 `tools/release/manifest.py` 独占，通过
  `python3 -m tools.release.build --version <version>` 构建。
- V4.9 是破坏性 current-only 迁移。回滚必须整体恢复物理模型、configuration、
  workspace、report schema、contracts 与 docs；不得混用旧人工 baseline、旧 deskew
  或旧 schema。
- 历史源码从 Git history 与 release tags 恢复，不在 current tree 复制 `archive/`。
