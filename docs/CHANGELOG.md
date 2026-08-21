# X5 Crop 更新日志

本文件只记录版本级行为与验证边界。当前合同见
[ARCHITECTURE.md](ARCHITECTURE.md)，当前目标与未闭风险见
[PROJECT_MEMORY.md](PROJECT_MEMORY.md)。

## V5（当前开发版本，尚未发布）

V5 只有一条 current-only runtime。被替代的 mode、schema、fallback、shim、Grid、完整链
materialization、平行 detector 和 report reuse 均不再支持。

### 用户行为

- 输入改为 format + 可选 count。省略 count 表示确认匹配片夹默认格数；明确 count 表示用户确认
  实际 slot 数，包括中间空白曝光格。Runtime 不再要求 full/partial mode。
- `135-dual` 默认且只自动处理 12 格、每 lane 6。其它 count 安全进入 review，不猜 lane 分配。
- 是否铺满在 placement 选定后按 outer 外侧能否再容纳一个 W 判断；不附加 gap，不提供长轴居中。
- 任一 slot 不安全时整张 source review。正式输出只发布到全新目录，不覆盖或接管旧结果。

### 模板对准

- Detector 改为有界模板编译器，并吸收 v4.2.8 的 whole-to-local 行为：先确定粗片带区域和共同
  方向，再在理论 outer、separator 和 top/bottom 附近做一次有界局部精修。
- Format 固定全部 frame 的 W/H。Role-free observation 只在模板提出理论角色后绑定；同一物理
  separator 的 edge、band 和多条 trace 不重复投票。
- Source pitch 由至少两个独立直接位置建立。缺失 first/last 可由已经获得 authority 的 phase、
  pitch 和 ordinal 投影；模板不能创造自己的 phase anchor。
- 两个 separator 的投影 phase 只有在另一份独立 direct support 闭合完整合法 fit 后才可晋升为
  authority；没有闭合时只保留其 pitch，不得把其它合法 placement 全部过滤。
- 未标 ordinal 的 separator 使用有界 lattice 对齐：source-wide material support 优先；否则只有
  唯一且极性闭合的局部 band 可提供 END→START 角色。Band 宽度本身不创造 local step。
- 偏差诊断明确区分 normal、一次 direct local step 与 unresolved。Wide/narrow 最多产生一次
  suffix shift；contact、overlap、多异常或 ordinal 不明保持 review。
- 全部 frame 共享 straight deskew direction。角色资格、source-wide 连续性和逐 trace 内外关系均
  闭合的轻微弯曲 sequence edge 可在有界异常点剔除后保留局部位置，但不提供全片方向，也不在
  straight anchor 已闭合全秩解时重标定 phase、W 或 pitch；残差进入 selected-placement safety，
  不建立曲线或逐帧方向。

### Cross 与输出保护

- Top/bottom 支持两种互斥用途：固定 H 的 `APERTURE_PAIR`，以及直接连续、完整包住 H 且总高度
  不超过 1.1H 的 `ENCLOSING_SUPPORT_PAIR`。后者可来自片夹或胶片材料支撑，但两侧不得与 aperture
  混用。
- Cross 单侧 aperture 现在允许一个 role-authorized direct binding 在 selected frame domains
  （数量至少为 3）中逐一拥有 direct trace，即使它的 aggregate independent support 只有两个
  区域；该权限不降低普通局部 two-region threshold，不拼接不连通 fragments，也不改变方向、
  role、fixed-H 或 output budget 约束。
- 短轴 coarse query 的 aggregate interval 仍只定位局部测量；同一批已注册 trace 若直接形成
  source-wide 双侧 track，可以独立提供共同方向和 enclosing support。Aggregate interval 不能因此
  获得照片边界权限。
- Aperture 正常 bleed 为 `max(0.15 mm, 0.7% W)` 和 cross 0.25 mm；四边完整 expansion 统一使用
  单边 5% 上限。Enclosing support 不加 cross bleed，使用总高度 1.1H 的独立合同。
- Enclosing support 的 1.1H 预算只读取直接 observation 的最坏 `observed_span`；不把不同联合可行
  状态的 top/bottom footprint 极值拼成并不存在的物理高度。
- 安全计算改为 selected-only 联合可行集合。Phase、pitch、direction、cross、local advance 和直线
  residual 的相关性一起传播，不把独立最大值相加，不合并 runner-up，不把越界 footprint 静默裁小。
- 二维内容只在 placement 唯一后作 negative veto，不能选位、移动边界或创造照片。

### 报告、工具与性能

- 冻结依赖同步到已验证环境：NumPy 2.5.2、tifffile 2026.8.16、imagecodecs 2026.8.16；安装器
  仍沿已确认 provider 只处理缺失或版本不符项，不建立第二套环境。
- Debug Analysis 使用 1800 px 宽、自适应高度的三联图，展示理论模板、实际观察、逐 role
  residual、direct/inferred ledger、best/runner、boundary use、最终 footprint、预算使用和根阻止
  事实；展示层不重算几何。
- Diagnostic summary 按根 review reason、blocking gap、phase/cross 状态、alignment pattern 和
  boundary use 聚合，并统计最小缺失事实、恢复类别和建议操作；仍不产生 accuracy verdict。
- 新增绑定 source SHA、configuration、measurement revision 与 plan identity 的开发 replay；它只复跑
  同一 phase/cross solver 输入，不携带真值，也不进入 production。
- 新增九张黄金的 v4.2.8 / V5 / 人工边界对照工具。它用于分清 coarse outer、最终 crop 与 bleed 的
  行为，不把历史版本当 reference，也不复制旧 Grid、score 或 fallback。
- Accuracy 在判断 nominal/challenge 与 final status 之前，先验证所有已选 candidate footprint
  是否覆盖用户确认边界；review 不再因正式输出被隐藏而跳过候选几何错误。批准结果仍另外验证
  正式输出的覆盖、直接使用预算与 deskew。
- Separator lattice hypothesis 是显式 receipt 工作量；编译上界不足时停止并进入 review，不做
  silent first-N。
- Performance profiler 覆盖完整用户路径，并拆分 startup/import、decode、gray/coarse support、
  registered measurement、template alignment/decision、sampling、encode/write、readback 和 publish。
- Performance receipt 在未插桩正式子进程中直接记录 peak RSS，并与 cProfile RSS、detector
  临时缓冲分开；5 秒均值仍是正式 Gate，3 秒均值新增为不阻断的 challenge。
- Registered gray 直接从原始 16-bit RGB 分块生成，不保留整张 float32 中间图；输出只对
  各 frame 做反向 affine ROI 采样，三通道复用预分配的坐标和值缓冲，不预先清零随后必定覆盖的
  输出，也不创建额外 uint16 分块；逐像素值与原采样合同一致。完全相同的 robust-line 输入才可
  复用精确结果，不剪枝、不改 observation 或 provenance。
- Affine ROI 在 lane authority 外只写黑色无数据像素，插值结果仍按完整 uint16 范围保留；测试同时
  覆盖非零照片像素、边界插值和 authority 外背景，避免几何通过但正式 TIFF 被写成全黑。
- 工具、tests、report 和 release manifest 只引用 current 模块与 schema；`tools/verify` 是唯一验证入口。
- Release contract 会实际构建临时 ZIP，校验路径唯一、排除 modular source/tests/tools、standalone
  与当前模块源码一致，并启动生成的 `X5_Crop.py --version`。
- v4/V5 黄金对照只接受正式九张 user-confirmed gold cohort；自定义 geometry 不得被标成黄金
  authority。Platform 聚合统一要求 Apple Silicon、Intel macOS 与 Windows x64 三份同 commit
  receipt，exFAT 无独立卷时保持显式 best-effort 未验证。
- 变形合同覆盖 coarse support 的边框平移、翻转、横竖转置与亮度/对比度，以及 phase 的平移、缩放
  和 fractional pitch；性能改动必须保持 solver 答案与 provenance。

### 验证边界

- 九张用户确认黄金决定几何准确性，当前九项均为 nominal，必须安全自动批准。任何黄金不得错误
  自动通过；未来 challenge 从安全 review 变为正确批准是允许的改进。
- 111-source diagnostic 只证明工程稳定、工作量、终态和 TIFF 合同。
- 24-source performance 的完整路径平均上限为 5 秒，3 秒为非阻断 challenge；receipt 只证明
  绑定的 commit、依赖和机器。
- 全部 release receipt 绑定同一 commit 以前，V5 不创建 RC、tag、Release 或公开 ZIP。

## V4.9（架构实验，不发布）

V4.9 建立 fixed-format template-first、source geometry、两级 Gate 与 source-coordinate safety，但
没有完成黄金 accuracy。它只存在于 Git history，不维护兼容路径。

## v4.2.8（当前稳定发布）

v4.2.8 证明了“先看整条片带，再在理论位置附近找 outer 和 separator”的行为能够快速覆盖绝大多数
规则片条。V5 继承理论 pitch、material band、有限局部搜索、缺边投影和正常快车道；不恢复旧
confidence、best-score、Grid 自证、content equal-split、固定像素 bleed 或 separator-center crop。

## 回滚

恢复历史版本时必须整体使用同一 commit 的 detector、configuration、schema、tests 与文档，不能
跨版本拼接组件。
