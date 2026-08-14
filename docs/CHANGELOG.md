# X5 Crop 更新日志

本文件只记录版本级行为与验证边界。当前合同见
[ARCHITECTURE.md](ARCHITECTURE.md)，当前实现差距与下一步见
[PROJECT_MEMORY.md](PROJECT_MEMORY.md)。

## V5（当前开发版本，尚未发布）

V5 只保留一条 current-only runtime；旧 schema、fallback、shim、AUTO、Grid、平行 detector 与
report reuse 均不再支持。当前完整合同见 [ARCHITECTURE.md](ARCHITECTURE.md)。

### 用户行为

- Format 由用户提供。Full 表示用户确认匹配片夹的完整铺满布局；partial 表示未铺满，必须提供
  `1 <= count <= full_count`，即使 count 相同也不获得长轴居中权限。`135-dual` 只允许 full。
- 固定格式为 135、half、XPan、120-645、120-66、120-67；120 短边统一为 56 mm。空白曝光始终
  占 slot，不做 blank suppression。
- 正式输入冻结为单页 16-bit RGB contiguous TIFF 与受支持无损压缩。Orientation 1–8 在读取边界
  规范化，输出写为 `Orientation=1`。
- 普通运行只在整张 source 可安全输出时写照片，否则整张进入 `needs_review`。Debug Analysis 只写
  诊断与 development facts；两种运行都从原 TIFF fresh detection。
- 输出只发布到全新目录。已有 target 直接拒绝，不覆盖、接管或删除用户文件。

### 检测与安全

- Detector 改为有界模板编译器：format、模式、count 与 holder authority 先编译固定 W/H、phase
  lattice、有限 measurement intents、工作量上界和停止条件；像素只负责对准、解释偏差和否决。
- Role-free edge 与 separator 只绑定模板角色，不再物化完整 chain。至少两个独立 adjacency 才能
  建立当前 source pitch；缺边由已支持 lattice 推导。直接 separator 最多授权两个 ordinal 已知的
  one-time suffix shift，不搜索异常位置。
- Cross 使用 role-authorized top/bottom、固定 H 和 source-wide 支持；单侧完整支持可推导另一侧。
  局部 fragment 不得靠坐标、trace 数或残差拼成 source-wide authority。每 lane 只保留 placement
  winner 与一个真正不同的 runner，不使用 scalar score、top-K 或 Pareto 票数补偿。
- 内容层只作负向否决。角落局部擦边、锯齿与尘点保持中性；只有离开角落并连续跨过边界不确定区间
  的可靠二维内容才否决 placement。
- 选择后的 placement 不可重新绑定。`SafeCropEnvelope` 只保护胜出 placement 自身的不确定性；5% start/end
  与 3% top/bottom 是逐边 direct-use 上限，不是 padding。
- 普通 report 只保存最终选择、安全框、budget、Gate 根因与输出；完整 observations、fit winner/runner、ledger、
  veto 与工作量只属于 Debug Analysis 和验证工具。
- Debug Analysis 分开绘制 observation、winner 与 runner，直接标出 runner 差异、phase 求解器记录的
  typed winner 依据和根 DecisionGate；最终输出面板不再把 review candidate 画成正式输出。

### 工程与验证

- OpenCV 只作有界像素测量；SciPy 只作拓扑、Huber 拟合与 affine sampling。测量校准集中在具名
  spec，不得进入 placement、投票或 Gate 成为隐藏规则。
- 检测灰度按有界行块生成，保持原逐像素结果，不再建立整张 float RGB 副本；正式裁切仍从原始
  16-bit RGB 采样。
- `tools/verify` 是唯一入口。Cohort 使用 SHA 和明确 count authority；工具不得从文件名、片夹容量或
  当前输出推导真值。Tests、tools 与 release manifest 只引用当前模块和 schema。
- 开发工具只服务正式验证、安装和发布；不保留没有消费者的 measurement replay 或自证测试。
- 日常 pre-push 只区分 documentation 与 full；performance 只在准备发布时绑定最终 release commit，
  不再阻塞普通提交和推送。
- 九项黄金决定几何准确性：nominal 必须安全自动批准，challenge 允许安全 review；111-source
  diagnostic 只验证工程稳定性；24-source performance 的正式 mean 上限为 5 秒。
- Full、diagnostic、performance、CI 或旧 receipt 都不能替代 accuracy 与真实平台证据。全部 release
  receipt 绑定同一 commit 前，V5 不可创建 RC、tag、Release 或公开 ZIP。

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
