# X5 Crop 更新日志

本文件只记录版本级行为与验证边界。当前合同见
[ARCHITECTURE.md](ARCHITECTURE.md)，当前实现差距与下一步见
[PROJECT_MEMORY.md](PROJECT_MEMORY.md)。

## V5（当前开发版本，尚未发布）

V5 是 current-only runtime。源码、CLI、schema、tests、tools 与 standalone 只保留当前 owner，
不提供旧 schema reader、fallback、shim、feature flag 或平行 producer。公开稳定版仍是
`v4.2.8`。以下记录已确认的 V5 版本合同；尚未对齐的实现只在
[PROJECT_MEMORY.md](PROJECT_MEMORY.md) 跟踪。

### 输入与物理模型

- Count authority 改为 `SlotCountRequest → MatchedHolder → ResolvedSlotCount`；holder matching 不再
  使用 requested count 过滤。Full 取匹配片夹的 `full_count`，partial 接受不超过该容量的用户明确
  count。调用级语法和匹配后的 count 冲突都在 detector 前以退出码 2 失败；交互入口返回
  mode/count 步骤。Holder identity 或 `full_count` 不唯一时保持 `needs_review`。
- Format 由用户提供；full 表示用户确认片条采用完整铺满布局，partial 表示没有铺满且允许
  `count == full_count`。只有 full 的正常完整链能够使用片夹长轴居中、总跨度和均匀排布权限；
  直接异常优先。片夹容量只校验上限，空白曝光仍占 slot；删除 `partial auto`，不实现 blank
  suppression。
- `135-dual` 改为 full-only，总计 12 格、每 lane 6 格。
- 120 格式冻结为 42×56、56×56 与 70×56 mm，不再保留 54 mm component。135、half、XPan
  的 format gap 先验分别为 2、1、2 mm；120 gap 保持未定义。
- Format 与片夹画布从一开始给出共享 W/H 窄范围；宽度兼容为 ±1.25%，高度为 ±0.40%。
  同一 source 不允许逐帧尺寸或旋转，齿孔不参与检测。
- Source 共享比例、W/H 与主方向族；每个 lane 独立拥有连续中心线、小角度偏差、phase、gap
  和异常。两段相容 pitch 是建立 `G_source` 的最低证据；异常不能从数学可能性枚举。
- Diagnostic 的 19 条历史 partial 与 performance 的 5 条历史 partial 已迁为显式 count；S053、
  S054、S056、S057 按 135 full 迁移。Runtime 不解析文件名 count，同 source SHA 的 mode/count/
  authority 必须一致。

### 检测、选择与安全

- `top/bottom` 只在 format 决定的窄走廊中聚合；`start/end` 主要由完整 separator band、共享 W
  和 ordinal chain 建立。内容层只作负向否决，缺少内容或边缘不等于安全证明。
- 原始内容事实为候选无关的 `ContentOccupancyObservation`，候选检查结果为
  `ContentVetoAssessment`。Start/end 外侧内容、接触或叠片的跨边内容保持中性；只有当前 slot
  内容被裁入或正常正 separator core 被可靠内容穿过才可否决。
- 角落局部擦边、边缘锯齿与尘点不再等同于切坏内容；二维结构必须离开相邻边角、跨过完整边界
  不确定区间，并在边界内外保持连续深度才具有 veto authority。
- Detector 先淘汰违反 format/count、共享几何、顺序、authority 或内容保护的完整链，再按直接
  物理证据、完整结构、separator 质量和弱先验分级比较。只统计独立观察，不使用任意加权总分。
- 多个候选不自动 review；明显胜出的完整 chain 可以批准。同等级的不同位置无法区分时保持
  `placement unresolved`，不平均、不任选，也不合并为大 union。
- Cross 与 sequence 分别产生有限 proposal，再按共享尺度、方向、中心线和 authority 做兼容索引
  联合；任何一轴不再提前选赢家，也不平均制造代表位置。
- 物理 edge family 在角色生成前按原始 transition、位置/方向区间与连续支持去重；只能整体共同拟合
  的连通 family 才合并。完整直接 separator 使用固定 W 的有向邻接路径，不再展开任意 role
  assignment；band 必须实际绑定对应 adjacency 才能计票。
- Selection 使用 sequence/cross/shared 三轴 Pareto dominance。便宜的物理过滤与分轴 frontier 在
  sampling、完整 ledger 与 Debug 物化前执行，不可比较者全部保留。
- 双 lane 的共享 W/H 在选择前绑定。选择后的物理 chain 以完整签名冻结，输出层不再重新求解或
  重新绑定 separator、角色、方向或边界。
- Format 决定固定照片框；`SafeCropEnvelope` 只包含胜出 placement 自身的测量不确定性，不合并
  落选候选，也不再添加固定或 format-specific minimum guard。接触或叠片时相邻输出可以共享
  source pixels。
- Producer 上限由去重后的 edge family、count 与合法角色推导，不再使用每 corridor 四条候选的
  经验上限；不允许 first-N、chain top-K、DP 或 beam。
- 竞争前只合并边界区间有共同交集、transform authority 相同且每 slot 最终 sampling box 完全
  相同的 cluster。跨 cluster 只按最高差异 evidence tier 的严格优势与同级可解释性判定 dominance，
  不使用隐藏总分。
- 5% start/end 与 3% top/bottom 是相对 format 尺寸的逐边最终上限，不是搜索范围或 padding。
- `CandidateGate` 只记录选择可信度与输出安全事实；`DecisionGate` 独占 final status 与 reasons。
  任一 slot 不安全时整个 source `needs_review`，不做 slot salvage。

### 运行、报告与输出

- 输入冻结为单页 16-bit RGB contiguous TIFF 与受支持无损压缩。Orientation 1–8 在 decode
  boundary 转为 canonical coordinates，正式输出写 `Orientation=1`；production 复开 header 做必要
  标签检查，完整像素复读留给 TIFF、platform 与端到端验证。
- `--debug-analysis` 执行同一检测与 Gate，只写三联诊断和 development report。普通运行始终从原
  TIFF fresh detection，不复用旧 report，不保留旧 revision reader。
- 普通 report 只保存最终选择、安全框、budget、Gate 根因和输出；全部 observation、chain、ledger、
  dominance、content veto 与 producer work 仅属于 Debug Analysis 和验证工具。
- 正式照片平铺在全新 target 根部。一次运行在同父目录 staging 写完后用一次 rename 发布；已有
  target 直接拒绝，不覆盖、不接管、不删除，不再建立 ownership inventory、lock、journal、磁盘
  预留或文件系统侦察。
- 生产默认 `--jobs 1`、上限 3；数值库内部线程固定为 1。依赖安装以模块能力和真实 provider
  为准，不建立 `.venv`，不叠加第二个 provider。
- OpenCV 只用于有界二维内容与底层像素测量，SciPy 只用于拓扑、Huber 直线拟合及 affine sampling。
  测量 spec、采样恒等量与物理/产品门槛分别归唯一 owner，不让经验量进入 placement 或 Gate。

### 验证与发布边界

- `tools/verify` 是唯一入口。九张黄金各运行一项，共九项；partial 只使用明确 count，不再运行
  auto 副本。111-source diagnostic 只验证工程合同，24-source performance 的正式 mean 上限为
  5 秒。
- 不增加样片规则、whitelist、format denylist、投票 margin 或验证专用 detector path，不能按
  format 或单样片调参。
- `full`、旧 receipt 或 CI 通过都不能替代 accuracy、performance 与真实平台证据。只有全部
  receipt 绑定同一 release commit，才可创建 RC、tag、GitHub Release 或公开 ZIP。
- 九项黄金 accuracy 未闭合前，即使工程、111-source diagnostic 与 24-source performance 通过，
  V5 仍不可发布。

## V4.9（架构实验，不发布）

V4.9 建立 fixed-format template-first、source geometry、两级 Gate 与 source-coordinate safety，
但没有完成黄金 accuracy。它只保留在 Git history，不再维护、打包或恢复兼容路径。

## v4.2.8（当前稳定发布）

v4.2.8 使用一维 profile、理论节距附近搜索、basic 优先和 enhanced 按需，取得良好速度与多数
场景的实用裁切。其多分段 profile、separator material、opposite-polarity edge pair、Grid
consensus 和有界局部复测已被 V5 物理模型吸收；confidence authority、固定 bleed、format
阈值、separator center 裁切和 best-score selection 不再使用。

## 回滚

恢复历史版本时必须整体使用同一 Git commit 的 detector、configuration、schema、tests 与文档，
不能跨版本拼接组件。
