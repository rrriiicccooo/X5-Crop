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
- 未标 ordinal 的 separator 使用有界 lattice 对齐：source-wide material support 优先；否则只有
  唯一且极性闭合的局部 band 可提供 END→START 角色。Band 宽度本身不创造 local step。
- 偏差诊断明确区分 normal、一次 direct local step 与 unresolved。Wide/narrow 最多产生一次
  suffix shift；contact、overlap、多异常或 ordinal 不明保持 review。
- 全部 frame 共享 straight deskew direction。轻微弯曲进入 selected-placement residual，不建立
  曲线或逐帧方向。

### Cross 与输出保护

- Top/bottom 支持两种互斥用途：固定 H 的 `APERTURE_PAIR`，以及直接连续、完整包住 H 且总高度
  不超过 1.1H 的 `ENCLOSING_SUPPORT_PAIR`。后者可来自片夹或胶片材料支撑，但两侧不得与 aperture
  混用。
- Aperture 正常 bleed 为 `max(0.15 mm, 0.7% W)` 和 cross 0.25 mm；四边完整 expansion 统一使用
  单边 5% 上限。Enclosing support 不加 cross bleed，使用总高度 1.1H 的独立合同。
- 安全计算改为 selected-only 联合可行集合。Phase、pitch、direction、cross、local advance 和直线
  residual 的相关性一起传播，不把独立最大值相加，不合并 runner-up，不把越界 footprint 静默裁小。
- 二维内容只在 placement 唯一后作 negative veto，不能选位、移动边界或创造照片。

### 报告、工具与性能

- Debug Analysis 使用 1800 px 宽、自适应高度的三联图，展示理论模板、实际观察、逐 role
  residual、direct/inferred ledger、best/runner、boundary use、最终 footprint、预算使用和根阻止
  事实；展示层不重算几何。
- Diagnostic summary 按根 review reason、blocking gap、phase/cross 状态、alignment pattern 和
  boundary use 聚合，并统计最小缺失事实、恢复类别和建议操作；仍不产生 accuracy verdict。
- 新增绑定 source SHA、configuration、measurement revision 与 plan identity 的开发 replay；它只复跑
  同一 phase/cross solver 输入，不携带真值，也不进入 production。
- 新增九张黄金的 v4.2.8 / V5 / 人工边界对照工具。它用于分清 coarse outer、最终 crop 与 bleed 的
  行为，不把历史版本当 reference，也不复制旧 Grid、score 或 fallback。
- Separator lattice hypothesis 是显式 receipt 工作量；编译上界不足时停止并进入 review，不做
  silent first-N。
- Performance profiler 覆盖完整用户路径，并拆分 startup/import、decode、gray/coarse support、
  registered measurement、template alignment/decision、sampling、encode/write、readback 和 publish。
- 工具、tests、report 和 release manifest 只引用 current 模块与 schema；`tools/verify` 是唯一验证入口。
- 变形合同覆盖 coarse support 的边框平移、翻转、横竖转置与亮度/对比度，以及 phase 的平移、缩放
  和 fractional pitch；性能改动必须保持 solver 答案与 provenance。

### 验证边界

- 九张用户确认黄金决定几何准确性。Nominal 不得降低正确自动通过率，任何黄金不得错误自动通过；
  challenge 从安全 review 变为正确批准是允许的改进。
- 111-source diagnostic 只证明工程稳定、工作量、终态和 TIFF 合同。
- 24-source performance 的完整路径平均上限为 5 秒；receipt 只证明绑定的 commit、依赖和机器。
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
