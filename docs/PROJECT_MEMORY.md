# 项目记忆

更新：2026-08-10

这是唯一跨会话检查点。长期政策见 [AGENTS.md](../AGENTS.md)，已确认的 V5 合同见
[ARCHITECTURE.md](ARCHITECTURE.md)，版本行为见 [CHANGELOG.md](CHANGELOG.md)。现场 Git、
源码、原 TIFF、current report、Debug Analysis 和最新命令输出始终优先。

## 当前目标

把现有 V5 current-only runtime 对齐到已确认的固定 format 框放置模型：物理事实约束候选，
分级独立证据选择明显胜出的完整 chain，胜出位置独占 `SafeCropEnvelope`，两级 Gate 分别审查
选择可信度与输出安全。V5 在实现、黄金 accuracy、性能和目标平台证据全部闭合前不发布；公开
稳定版仍为 `v4.2.8`。

## 已确认检查点

- Format/count 是硬输入。Partial 只接受用户明确 count，包含空白曝光格；片夹容量只校验上限，
  不再提供 auto。V5 不删除空白 slot。
- Format 尺寸、gap 先验、共享 W/H、方向、中心线、`G_source`、separator chain、接触/叠片、
  top/bottom 与 start/end 的物理和证据语义已由 [ARCHITECTURE.md](ARCHITECTURE.md) 冻结。
- 选择以完整 chain 为单位，先比较证据等级，再比较同等级独立观察；弱先验不能击败直接物理
  证据。没有明显胜出者才 `placement unresolved`。
- `SafeCropEnvelope` 只保护胜出 format placement 自身的不确定性，不合并落选位置，不重复添加
  guard。逐边 5%/3% 只验证最终 direct-use 输出。
- 文档已按职责同步：公共文档只写用户行为，架构保存合同，更新日志保存版本差异，本文件只保存
  当前实现差距和下一步。本次同步不构成源码、accuracy、performance 或平台验证。

## 开放实现差距

1. 输入仍需删除 `partial auto`，让 CLI 要求明确 count，并让启动器在缺失、无效或超过容量时
   重新询问。
2. Format catalog 仍需删除 120 的 54 mm component，冻结 135/half/XPan gap 先验并让 120 gap
   保持 unresolved；所有齿孔依赖必须为零。
3. `frame_height_tolerance_ratio` 当前实现为 2.00%，属于历史调试漂移；已确认合同是 0.40%。
   宽度合同为 1.25%。
4. Geometry 仍需落地共享 W/H、连续中心线、两段 pitch 建立 `G_source`、正常链优先和证据驱动
   的接触/叠片/大间隙。
5. Selection 仍需从旧 retained-placement union/代表解语义收敛为完整 chain 的分级独立证据投票；
   `SafeCropEnvelope` 必须改为胜出位置自身不确定性，删除额外 minimum guard。
6. `CandidateGate`、`DecisionGate`、report 与 Debug Analysis 仍需消费新的 vote ledger、
   observed/inferred、竞争者和 review reasons。精确全局胜出 margin 尚未用黄金样片冻结。

## 验证边界与风险

- 当前源码行为不能因文档已更新而声称符合新合同。旧黄金、111-source、performance 或平台
  receipt 都不能证明未来实现，也不能迁移到检测变更后的 tree。
- 物理模型已闭合，但具体 detector 能否从真实 TIFF 稳定生成所需观察仍须用用户确认黄金验证。
  真值歧义保持 unresolved，不从算法输出自动生成 baseline。
- 111-source diagnostic 只证明工程稳定和工作量有界，不证明位置投票正确。
- 任何为单一样片增加的阈值、format 特例、whitelist 或更容易通过的验证路径都不可接受。

## 精确下一步

1. 只读审计源码与测试，把上述六类差距逐项映射到唯一 owner，形成不恢复旧路径的实现计划。
2. 按输入/catalog、共享 geometry 与 evidence、chain voting 与 `SafeCropEnvelope`、Gate/report/debug
   四个边界批次实施；每批同步删除被替代的 API、schema、tests 和 dead code。
3. 每个批次先运行相应 unit/full；检测合同完成后统一重跑十四项黄金、challenge、111-source
   diagnostic、24-source 两遍性能与全局残留审计。
4. 只在最终 release commit 上重新生成 Apple Silicon、Windows x64、Intel macOS 与文件系统
   receipt，再决定是否制作 RC。
