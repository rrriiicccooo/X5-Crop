# X5 Crop 更新日志

本文件只记录版本级行为与验证边界。当前合同见
[ARCHITECTURE.md](ARCHITECTURE.md)，当前目标与风险见
[PROJECT_MEMORY.md](PROJECT_MEMORY.md)。

## V5（当前开发版本，尚未发布）

V5 只有一条 current-only runtime；历史 mode、schema、fallback 与平行 detector 只保存在 Git history。

### 产品行为

- 用户提供 format，并确认匹配片夹的默认 count 或显式 count；count 包含中间空白曝光格。Runtime 不猜
  format、照片数或 blank，也没有 full/partial mode。`135-dual` 只有 12=6+6 可自动处理。
- Detector 改为有界 fixed-template-first：从整条片带建立 coarse support，再在 format/count 编译出的
  outer、separator 与 top/bottom 邻域一次测量。Format 设计 W/H、source-level aperture 与 typed evidence
  决定 phase、pitch、cross 和 ordinal；每个唯一绑定的直接 separator 可以约束自己的 local advance，
  全部变化仍只作一次 O(count) 传播。像素强度、片夹中心或样片规则不能替代 authority。
- Separator material 在同一个 registered measurement owner 内完整支持 `dark | light` polarity。相邻
  反向 edge 必须在同一高度区域同时满足 oriented tone contrast 与 core texture 合同；局部两区域 support
  不能冒充 source-wide role authority，完整三区域反证产生 typed `separator_material_conflict`。超出 normal
  gap 上界的 material 仍保留为事实，但不能创造 phase、ordinal 或直接角色权限。
- 已登记 sequence trace 的弱 gradient、tone 与 texture 可在三个固定高度区域内联合成一份 typed
  observation。只有位置、方向、polarity 与角色相容的三区域结果唯一绑定同一条局部 direct edge 时，
  才以 `cross_height_union` 加强该 edge；standalone、重复或多解联合线只进入 development report 与
  Debug，不进入 phase、separator、outer 或 placement，也不重复计票或增加 TIFF 读取。
- 直接观察到的 start/end 在最终 placement 中保留 native coordinate 与完整 interval；Grid 只补齐缺失
  角色。同一连续 placement 的互补 endpoint evidence 合并为联合可行状态，不伪造 runner。唯一 placement
  中至少两张完整直接 Frame 可闭合 source W；当每个缺失 Frame 仍有一侧直接边缘时，同一份相关 W 可补
  多条 opposite。任一 Frame 双侧都未观察，或共同 W authority 不足时，产生 typed
  `frame_width_inference_unavailable`。缺失 separator 只有在
  直接约束矩阵独立闭合 `phase/W/pitch`、对应 adjacency 的完整不确定性走廊被已执行窗口逐 trace 覆盖、
  且没有局部反证时才按 `local_delta = 0` 补齐；不再用 edge 数、连续缺失数或全局 query-complete
  布尔值代替证明。候选无关 sequence 窗口按左右 holder 端分别投影完整且相关的 `W/pitch` 状态，覆盖
  传播走廊但不重复相加互斥极值；扩大 ownership 不增加 TIFF 读取。带 Grid 推断的 placement 还要求
  首尾输出 Frame 各至少绑定一条直接长轴角色，不能由片夹位置凭空创造整张外侧 Frame。任一已选直接
  START/END 只有获得 source-wide edge、同一 separator pair 或独立 fixed-W Frame pair 的坐标权限后，
  才能进入最终 placement；局部孤立 edge 保留为观察并产生 typed review，不能反向参与 lattice 自证。
- Format W/H compatibility 由一个 current-only 混合物理合同统一计算：
  `guard_W=max(0.95 mm, 2.4%W)`、`guard_H=max(0.70 mm, 1.8%H)`。参数来自 105 个合格黄金 source、
  494 个完整且全部直接可见 Frame 的 source-level 中位尺寸、分轴长 q95 与向外量化；不再保存 `half`
  或其它 format 的 tolerance 特例。Direct complete Frames 以完整 uncertainty 收紧 source W，唯一直接
  aperture pair 收紧 source H，native boundary 始终优先。
- `ApertureAspectRatioAuthority` 已启用：各 format 的 source-level raw W/H 包络由两轴混合 guard 传播成
  format-specific guarded ratio，再从至少两张完整直接 Frame 闭合的 W 推导一份 rank 0 相关 H。
  Calibration/共同 scale/W authority 不足、physical prior 冲突、direct H 冲突与 5% 预算耗尽均有 typed
  failure；direct H 存在时优先承担 cross。没有合格黄金数据的 format 保守 review，不作精确名义比例换算。
- Separator 仍以 catalog gap 为搜索中心，实际宽度由直接 material edges 与 local advance 拥有；holder
  extent 保留独立的外部 ±3.5% 设计先验。二者都没有为了复用 aperture guard 而改变物理含义。
- Cross 注册超过编译上界时不再抛出 runtime error；完整实际计数进入 typed `producer_bound_exceeded`
  receipt，并由 Gate 安全 review，不截断观察或提高魔法上限。
- Cross registration 现在是同角色边界 family identity 的唯一 owner。只有一次 robust refit 精确保留完整
  transition union 时，多个局部 fragment 才合并为一个 canonical observation；refit 丢失任一 transition
  时全部成员原样保留，并报告 typed `complete_transition_union_refit_rejected`。Selection 中旧的
  broader/local dominance 已删除；不再按 trace containment、邻近、support 或 residual 消除 runner。
- 当前选择仍只使用 typed hard facts；没有启用 score。架构允许未来在硬合法候选之间加入经独立数据
  校准、带高阈值与 abstention 的概率选择，但未经校准的 score 不得拥有最终决定权，runner
  必须继续报告。
- Cross 不再用片夹短轴中心选择最终边界；它只帮助编译有界测量 corridor。直接 top/bottom pair 现在显式
  区分 `shared_traces` 与 `complementary_domains`：后者只在两侧都是 role-authorized direct evidence、
  各自有至少两个独立区域、两侧 trace 并集完整覆盖全部 selected Frame domain，且 fixed H 与方向相容时
  成立；共享 trace 数仍如实为 0。缺 domain、template-local/inferred opposite、方向冲突或多个完整 pair
  均保留 typed failure 与 review。若完整 pair 的同一 opposite 还能与严格更外侧的直接局部 role 闭合，
  内侧 pair 产生 typed `outward_role_counterevidence`；更外侧 pair 若也拥有完整 authority，则两者继续作为
  非等价 placement review。Source-spanning 单侧也不再把未覆盖全部 selected domain 的局部 opposite 外推
  为整条片带边界。Cross winner basis、pair support mode、family resolution、source 长轴投影
  与 enclosing-support 的逐侧/联合 padding 预算进入 typed report 和 Debug。已经由 fixed H 与 `1.1H`
  合同预闭合的唯一 enclosing-support pair 直接拥有两侧输出权限，不再错误依赖或消费只用于缺失
  aperture side 的 W/H 比例推导。
- 任一 slot 不安全时整张 source `needs_review`，不做 slot salvage。Contact 与 overlap 始终属于
  challenge，但 challenge 不预设终态：标准 detector/Gate 可产生安全自动批准，证据不足时安全 review
  同样合格。当前尚未启用异常 topology；后续只允许在同一 adjacency/placement 中加入显式关系，并让
  受影响边界的 topology protection 消耗既有 5% 总预算，不建立第二套 detector 或独立特殊 bleed 预算。
- Placement 保持 source-axis；局部直线 slope 只扩大安全包络。Deskew 是批准后的可选整理，不参与
  placement、Gate 或黄金准确性；证据不足或超限时保持原始倾斜。
- 安全层只处理唯一 selected placement 的联合可行状态。Aperture 每侧共用 5% 外扩预算；直接 enclosing
  support 使用总高度不超过 `1.1H` 的独立合同。所需 footprint 越出 authority 时 review，不静默裁小。
- 二维 content 只对最终 post-residual、post-bleed polygon 作 negative veto；它不能移动边界、选择
  runner 或创造 phase。

### 输出与报告

- Finalization 对 source 与安全 polygon 使用同一 affine transform，再取精确半开 AABB；不在旋转后继续
  裁固定 W×H。AABB 的 no-data 角落不是检测失败。
- Debug Analysis 只可视化同次检测事实：理论模板、观察、winner/runner、最终 footprint、预算和首个
  阻断原因；报告同时保存全局未知量 constraint rank、逐 adjacency query/trace/coordinate coverage 与
  直接角色/外侧 Frame observation authority，以及 dark/light material、逐区域状态和冲突。Debug 不重新
  求解，也不把 review candidate 伪装为正式输出。当前 report revision 为
  `x5crop_v5_template_report_20`，并显式报告 source W/H、相关 Frame-width inference、aspect calibration、
  raw/guarded ratio、两轴 guard、推导 H、Cross typed root failure、pair support mode、family resolution 与
  预算；不保留旧 schema 兼容路径。
- 正式 TIFF 保真 16-bit RGB、ICC、resolution、支持的 metadata 与无损压缩，并写
  `Orientation=1`。完整 source 先写 staging，再原子发布到尚不存在的目录。
- Report、Gate 与 final geometry 各有唯一 owner；`CandidateGate` 只记录事实，`DecisionGate` 创建终态。

### 黄金校准

- 本地标注器使用一个 source-SHA-bound 校准池；不区分 v1/v2。同源多 count 共用一套物理边界，各自
  保留 task mapping，不建立重复页签或重复确认。
- Source record 以两条共享边、一个 `boundary_pool`、typed `slots` 和派生 `adjacencies` 表达几何。
  `blank_exposure` 保留 count/ordinal 但没有人工边界；`source_truncated` 保存物理外推线与 TIFF 内交集。
- 红线导入、机器 proposal、有界预览与原 TIFF 窄带精修都不授予黄金权限。逐线
  `review_basis`、Frame 状态、原生像素审核与明确确认完成后，source 才成为不可变
  `user_confirmed`。
- 黄金验收统一为最内侧可接受无 bleed 裁切：candidate 与正式 footprint 不得向确认 polygon 内侧
  越界；有预算权限的每侧最多向外 5%。`visible_content_limit` 只阻断向内越界，
  `human_width_estimate` 两向均不阻断，其它边仍独立生效。
- 人工红线尽量贴近该 source 的真实有效成像边界，基本可作为 source aperture 的尺寸观测。黄金分析
  按 source SHA 分开统计同源与跨 source 的 W/H、separator 和 pitch；这些事实可校准物理分布与
  source-level authority，但不能被压成适用于所有相机的单一固定常量。偏离 catalog 时先检查相机个体
  差异、扫描比例和 uncertainty，不自动归咎于标注。
- Nominal/challenge 在 detector 运行前由人工证据和固定模板合同逐 task 派生，并随确认基线冻结；
  accuracy 会重新推导核对，不能手填改类。Nominal 以安全自动批准为能力目标；challenge 的安全 auto 与
  安全 review 都有效，前者单独记录为能力发现。
- 两侧各空余至少一个固定 W、又缺少双端直接 outer 的内部 partial sequence 属于 challenge；该角色只从
  确认前几何推导，不由当前 detector 的结果或 post-selection holder fill 决定。
- Accuracy 只接受当前确认 task。没有完整的当前 development cohort 时明确报告
  `calibration is incomplete`，不回退历史基线。空 slot 不参与几何比较，但 runtime 对应输出与 ordinal
  必须保留。
- 完整确认集合通过唯一生成器独立核对 source、确认快照、审阅 artifact、task authority、角色和 geometry
  digest 后，才写入 tracked development cohort。Development 黄金分析把基础 nominal、较难 nominal 与
  challenge 分开，并逐边区分已观察且绑定、已观察未绑定、模板补全和竞争状态；这些诊断不进入 runtime
  或黄金权限。
- 当前已查看黄金明确归入 `development_gold`；未来 sealed acceptance 必须在查看 detector 结果前按
  source SHA 分区，同源 count 同分区，解封调试后永久退役到 development。人工 reference 仍只有一套。
- 验证分别报告危险自动批准、Review candidate 几何、nominal 自动覆盖和 challenge 能力；只有正式
  `approved_auto` 越过黄金安全合同才是用户层危险输出。
- 同源合法 count 变体按共享物理 Frame 建立 source-level diagnostic；额外空白或残缺 slot 不得把共享
  内容重定相到危险位置，但不同 count 可以合法产生不同 auto/review 终态。

### 工程与验证

- `tifffile + imagecodecs` 独占正式 TIFF I/O；OpenCV 只作有界像素测量，SciPy 只作数值与 sampling，
  Pillow 只在 Debug Analysis 延迟导入。生产默认 `--jobs 1`、上限 3，内部数值线程固定为 1。
- Phase residual compatibility 在物理阈值处保持包含语义，并只吸收 `1e-9 px` 的浮点舍入误差；不同
  NumPy/LAPACK 构建不得因此改变 `resolved/ambiguous`。对应阈值与独立支持回归随 full/pre-push
  验证执行。
- Registered gray、affine crop buffer 与 source-local cache 按阶段释放；这些优化不得改变 observation、
  placement、Gate、footprint 或输出像素。
- `tools/verify` 是 Hook、CI 与本地验证的唯一入口。Diagnostic 只证明工程合同；gold accuracy、性能与
  platform receipt 分层记录，不互相冒充。
- 正式性能 Gate 为 24-source 完整用户路径 mean 不超过 5 秒；3 秒只是不阻断的 challenge。
- Enclosing-support 权限检查点 `728450da` 的完整 development gold 为 110/110 完成、分析错误 0、
  `unsafe_approved_auto = 0`；安全 auto 为基础 nominal 6/66、较难 nominal 0/30、challenge 0/14。基础
  nominal candidate 为 47 个不可用、13 个安全、6 个不安全，所有不安全 candidate 均保持 review。
  黄金重算也继续确认 105-source/494-Frame W/H calibration 的运行时公式、计数与 source-level q95 一致。
- 同 commit 的 24-source 正式 mean 为 2.944 秒，5 秒 Gate 通过，3 秒 non-blocking 目标达到。当前其余
  review 表达真实的 phase/cross、source-footprint 与预算证明缺口，不以调窄 guard、静默裁小 footprint、
  恢复精确 W→H 或改变样片角色掩盖。
- Apple Silicon macOS、Intel macOS 与 Windows x64 必须在同一最终 commit 取得实机 receipt。Accuracy、
  性能与平台证据未全部绑定该 commit 前，不创建 RC、tag、Release 或公开 ZIP。
- 发布包由唯一 manifest 构建，不包含 modular source、tests、tools、内部文档或开发输出。

## V4.9（架构实验，不发布）

V4.9 建立 fixed-format template-first、source geometry、两级 Gate 与 source-coordinate safety，但没有
完成黄金 accuracy。它只存在于 Git history，不维护兼容路径。

## v4.2.8（当前稳定发布）

v4.2.8 证明“先看整条片带，再在理论位置附近找 outer 和 separator”可以快速覆盖规则片条。V5 继承
理论 pitch、material band、有限局部搜索与缺边投影，不恢复旧版未经校准且直接决定终态的 confidence /
best-score、Grid 自证、content equal-split、固定像素 bleed 或 separator-center crop。

## 回滚

恢复历史版本必须整体使用同一 commit 的 detector、configuration、schema、tests 与文档，不能跨版本
拼接组件。
