# 项目记忆

更新：2026-08-10

这是唯一跨会话检查点。长期政策见 [AGENTS.md](../AGENTS.md)，已确认的 V5 合同见
[ARCHITECTURE.md](ARCHITECTURE.md)，版本差异见 [CHANGELOG.md](CHANGELOG.md)。现场 Git、
源码、原 TIFF、current report、Debug Analysis 和最新命令输出始终优先。

## 当前目标

把唯一 V5 current-only runtime 对齐到固定 format 框放置合同：由物理事实产生和淘汰完整 chain，
按证据等级与独立观察选择明显胜出者，只为胜出 placement 生成最小 `SafeCropEnvelope`，再由
两级 Gate 分别审查选择可信度与输出安全。实现、黄金 accuracy、性能和目标平台证据全部闭合前
不发布 V5；公开稳定版仍为 `v4.2.8`。

## 当前检查点

- [ARCHITECTURE.md](ARCHITECTURE.md) 已集中保存讨论确认的 format、尺度、间隙、中心线、
  top/bottom、separator chain、内容否决、完整链投票、`SafeCropEnvelope` 与 Gate 合同。公共文档只
  保存用户可见行为。本轮只有文档变化，不构成实现或验证证据。
- 现场源码仍保留可复用的 template-first、registered measurement、Grid/edge-pair 基础、两级
  Gate、TIFF 事务和严格 Debug Analysis report reuse；新实现应在这些 current owner 上收敛，
  不恢复历史 detector 或建立平行路径。
- 现场搜索未发现齿孔 detector。无齿孔依赖是应保持的现状，不是新增实现任务。

## 开放实现差距

1. `FrameCountMode.AUTO` 仍贯穿 CLI、交互启动器、runtime、Gate、report、regression cohort 和
   tests。Partial 必须改为明确 count；启动器只保留重新输入，片夹容量只校验上限。现有九张
   黄金因五张 partial 的 explicit/auto 副本形成十四项，需收敛为九张各一项；diagnostic、
   performance 和 platform cohort 的每个 partial source 也必须保存明确 count，不得从容量或
   filename 推导。现场分别有 51/111、9/24、1/6 条 partial 记录缺少该字段，须取得独立 count
   authority 后才能继续作为完整检测验证样片。Count/schema 改变后，旧 auto report 必须失效并
   重新检测。
2. Format catalog 仍包含 120 的 54 mm component、format-owned 固定 local-gap 区间以及旧 gap：
   135 为 1.625 mm、XPan 为 2.5 mm、120 族均有固定值。合同要求只保留 56 mm 短边，135/half/
   XPan 分别使用 2/1/2 mm 搜索先验，120 `G_format` 必须在数据合同中显式表示为 unresolved，
   不能用零或固定局部区间代替；异常 gap 只由证据决定。
3. `frame_height_tolerance_ratio` 当前为 2.00%，属于未获确认的 S027 调试漂移；用户确认合同为
   0.40%。宽度 1.25% 已正确。共享 W/H、连续中心线、两段 pitch 建立 `G_source`、正常链优先和
   negative-only content veto 仍需在同一 geometry/evidence path 落地。
4. 当前 selection 仍保存 `CanonicalFormatPlacement`、全部 retained placements 的 safety union 与
   format-specific minimum guard。它必须改为完整 chain 的分级独立证据投票，并只保留胜出位置
   自身的测量不确定性。
5. `CandidateGate`、`DecisionGate`、report 与 Debug Analysis 尚未消费新的 vote ledger、
   observed/inferred、竞争者淘汰依据和细分 review reasons。精确全局胜出 margin 也尚未由黄金
   样片冻结。

## 验证边界与风险

- 文档合同不能证明当前源码已经具备新行为。Source-SHA-bound、用户确认的黄金坐标仍是 reference
  authority；但旧 accuracy 结果、111-source 结果、performance 和平台 receipt 都不能迁移为
  新 tree 的证据。
- 物理关系已经明确，但真实 TIFF 能否稳定提供所需边缘、separator 与内容否决观察，仍须以
  用户确认黄金验证；算法输出不能自动成为 baseline。
- 111-source diagnostic 只证明工程稳定和工作量有界，不证明 chain 选择正确。
- 不接受单一样片阈值、format 特例、whitelist、denylist 或验证专用 detector path。
- `origin/main` 仍在 `bc962308`；当前文档更新只在本地 main，待用户明确授权外部推送。

## 精确下一步

1. 在不修改源码的前提下，把五类差距映射为 current owner、数据合同、删除项和验证项，形成一次
   可审查的实现计划。
2. 获得实施确认后，按 count/catalog、共享 geometry/evidence、chain selection/`SafeCropEnvelope`、
   Gate/report/debug 四个边界批次修改；每批同步删除被替代的 API、schema、tests 和 dead code。
3. 每批先运行对应 unit/full；检测合同完成后统一重跑九项黄金、111-source
   diagnostic、24-source 两遍性能与全局残留审计。
4. 只在最终 release commit 上生成 Apple Silicon、Windows x64、Intel macOS 与文件系统 receipt，
   再决定是否制作 RC。
