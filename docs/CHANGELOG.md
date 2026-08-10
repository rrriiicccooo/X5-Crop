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
  使用 requested count 过滤。Full 取匹配片夹的 `full_count`，partial 只接受更少的用户明确
  count。调用级语法错误以退出码 2 失败，匹配后的 partial 冲突为 source `runtime_error`；holder
  identity 或 `full_count` 不唯一时保持 `needs_review`。
- Format 由用户提供；full 表示完整固定 slot 数，partial 只接受更少的用户明确 count。模式不再
  表示片条是否铺满片夹，也不决定首尾位置或 Grid phase。片夹容量只校验上限，空白曝光仍占
  slot；删除 `partial auto`，不实现 blank suppression。
- 120 格式冻结为 42×56、56×56 与 70×56 mm，不再保留 54 mm component。135、half、XPan
  的 format gap 先验分别为 2、1、2 mm；120 gap 保持未定义。
- Format 与片夹画布从一开始给出共享 W/H 窄范围；宽度兼容为 ±1.25%，高度为 ±0.40%。
  同一 source 不允许逐帧尺寸或旋转，齿孔不参与检测。
- 每个 lane 共享主方向和连续中心线。正常间隙优先；两段相容 pitch 是建立 `G_source` 的最低
  证据。接触、叠片、大间隙和相位跳变必须有证据，不能从数学可能性枚举。
- Diagnostic 的 19 条历史 partial 与 performance 的 5 条历史 partial 已迁为显式 count；S053、
  S054、S056、S057 按 135 full 迁移。Runtime 不解析文件名 count，同 source SHA 的 mode/count/
  authority 必须一致。

### 检测、选择与安全

- `top/bottom` 只在 format 决定的窄走廊中聚合；`start/end` 主要由完整 separator band、共享 W
  和 ordinal chain 建立。内容层只作负向否决，缺少内容或边缘不等于安全证明。
- 原始内容事实为候选无关的 `ContentOccupancyObservation`，候选检查结果为
  `ContentVetoAssessment`。Start/end 外侧内容、接触或叠片的跨边内容保持中性；只有当前 slot
  内容被裁入或正常正 separator core 被可靠内容穿过才可否决。
- Detector 先淘汰违反 format/count、共享几何、顺序、authority 或内容保护的完整链，再按直接
  物理证据、完整结构、separator 质量和弱先验分级比较。只统计独立观察，不使用任意加权总分。
- 多个候选不自动 review；明显胜出的完整 chain 可以批准。同等级的不同位置无法区分时保持
  `placement unresolved`，不平均、不任选，也不合并为大 union。
- 每个 sequence/cross 组合独立物化；删除先平均多个 cross 候选再生成代表位置的旧逻辑。
- Format 决定固定照片框；`SafeCropEnvelope` 只包含胜出 placement 自身的测量不确定性，不合并
  落选候选，也不再添加固定或 format-specific minimum guard。接触或叠片时相邻输出可以共享
  source pixels。
- Producer 上限固定为每 corridor 4 band、每 lane 8 complete chain、每 chain ledger 64、每 lane
  ledger 512、双 lane source 1024；触发任一上限都产生 `producer_bound_exceeded` 并阻断批准。
  未物化 proposal 只报告数量与固定 reason，不保存无界 payload。
- 竞争前只合并边界区间有共同交集、transform authority 相同且每 slot 最终 sampling box 完全
  相同的 cluster。跨 cluster 只按最高差异 evidence tier 的严格优势与同级可解释性判定 dominance，
  不使用隐藏总分。
- 5% start/end 与 3% top/bottom 是相对 format 尺寸的逐边最终上限，不是搜索范围或 padding。
- `CandidateGate` 只记录选择可信度与输出安全事实；`DecisionGate` 独占 final status 与 reasons。
  任一 slot 不安全时整个 source `needs_review`，不做 slot salvage。

### 运行、报告与输出

- 输入冻结为单页 16-bit RGB contiguous TIFF 与受支持无损压缩。Orientation 1–8 在 decode
  boundary 转为 canonical coordinates，正式输出写 `Orientation=1` 并复读验证。
- `--debug-analysis` 执行同一检测与 Gate，只写三联诊断和报告类文件。后续普通运行仅在 current
  schema、完整性、版本、source identity、TIFF profile、配置和 layout 全部匹配时复用报告。
- Report 与 Debug Analysis 显示胜出 chain、独立证据、observed/inferred、竞争者、
  holder/count authority、有界 producer/ledger、sampling cluster、content veto、`SafeCropEnvelope`、
  逐边 budget 与 Gate reason，不能只显示总分。
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
- 当前实施阶段明确不运行黄金 accuracy；即使工程、111-source diagnostic 与 24-source
  performance 通过，仍只能称为实现候选。用户尚未人工开启并完成九张黄金验证时，V5 不可发布。

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
