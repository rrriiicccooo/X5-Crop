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

- Format 由用户提供；full 使用固定 count，partial 只接受用户明确输入的曝光格数。片夹容量只
  校验上限，空白曝光仍占 slot；删除 `partial auto`，不实现 blank suppression。
- 120 格式冻结为 42×56、56×56 与 70×56 mm，不再保留 54 mm component。135、half、XPan
  的 format gap 先验分别为 2、1、2 mm；120 gap 保持未定义。
- Format 与片夹画布从一开始给出共享 W/H 窄范围；宽度兼容为 ±1.25%，高度为 ±0.40%。
  同一 source 不允许逐帧尺寸或旋转，齿孔不参与检测。
- 每个 lane 共享主方向和连续中心线。正常间隙优先；两段相容 pitch 是建立 `G_source` 的最低
  证据。接触、叠片、大间隙和相位跳变必须有证据，不能从数学可能性枚举。

### 检测、选择与安全

- `top/bottom` 只在 format 决定的窄走廊中聚合；`start/end` 主要由完整 separator band、共享 W
  和 ordinal chain 建立。内容层只作负向否决，缺少内容或边缘不等于安全证明。
- Detector 先淘汰违反 format/count、共享几何、顺序、authority 或内容保护的完整链，再按直接
  物理证据、完整结构、separator 质量和弱先验分级比较。只统计独立观察，不使用任意加权总分。
- 多个候选不自动 review；明显胜出的完整 chain 可以批准。同等级的不同位置无法区分时保持
  `placement unresolved`，不平均、不任选，也不合并为大 union。
- Format 决定固定照片框；`SafeCropEnvelope` 只包含胜出 placement 自身的测量不确定性，不合并
  落选候选，也不再添加固定 guard。接触或叠片时相邻输出可以共享 source pixels。
- 5% start/end 与 3% top/bottom 是相对 format 尺寸的逐边最终上限，不是搜索范围或 padding。
- `CandidateGate` 只记录选择可信度与输出安全事实；`DecisionGate` 独占 final status 与 reasons。
  任一 slot 不安全时整个 source `needs_review`，不做 slot salvage。

### 运行、报告与输出

- 输入冻结为单页 16-bit RGB contiguous TIFF 与受支持无损压缩。Orientation 1–8 在 decode
  boundary 转为 canonical coordinates，正式输出写 `Orientation=1` 并复读验证。
- `--debug-analysis` 执行同一检测与 Gate，只写三联诊断和报告类文件。后续普通运行仅在 current
  schema、完整性、版本、source identity、TIFF profile、配置和 layout 全部匹配时复用报告。
- Report 与 Debug Analysis 显示胜出 chain、独立证据、observed/inferred、竞争者、
  `SafeCropEnvelope`、逐边 budget 与 Gate reason，不能只显示总分。
- 正式照片平铺在 target 根部。新结果通过 owner、inventory、lock、journal 与同父目录 rename
  安全发布；状态歧义保留所有候选，不猜测删除。
- 生产默认 `--jobs 1`、上限 3；数值库内部线程固定为 1。依赖安装以模块能力和真实 provider
  为准，不建立 `.venv`，不叠加第二个 provider。

### 验证与发布边界

- `tools/verify` 是唯一入口。九张黄金各运行一项，共九项；partial 只使用明确 count，不再运行
  auto 副本。111-source diagnostic 只验证工程合同，24-source performance 的正式 mean 上限为
  5 秒。
- 不增加样片规则、whitelist、format denylist 或验证专用 detector path。投票 margin 必须在
  用户确认黄金上全局验证，不能按 format 或单样片调参。
- `full`、旧 receipt 或 CI 通过都不能替代 accuracy、performance 与真实平台证据。只有全部
  receipt 绑定同一 release commit，才可创建 RC、tag、GitHub Release 或公开 ZIP。

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
