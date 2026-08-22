# X5 Crop 更新日志

本文件只记录版本级行为与验证边界。当前合同见
[ARCHITECTURE.md](ARCHITECTURE.md)，当前目标与开放风险见
[PROJECT_MEMORY.md](PROJECT_MEMORY.md)。

## V5（当前开发版本，尚未发布）

V5 只有一条 current-only runtime。被替代的 mode、schema、fallback、shim、Grid、完整链
materialization、平行 detector 和 report reuse 均不再支持。

### 产品行为

- 用户提供 format，并确认匹配片夹的默认 count 或明确 count；count 包含中间空白曝光格。Runtime
  不猜 format、照片数或 blank，也不保存 full/partial mode。
- `135-dual` 只自动处理 12 格、每 lane 6 格；其它 count 安全进入 review。任一 slot 不安全时整张
  source review，不做 slot salvage。
- Detector 改为有界 fixed-template-first 对准：先建立 role-free coarse support，再在固定 outer、
  separator 和 top/bottom 窗口一次登记、一次测量。Format 固定 W/H，像素 observation 只负责对准、
  解释最多一次 direct wide/narrow local advance，并否决非法 placement。
- Phase、pitch、cross、ordinal、content 和 holder fill 使用 typed physical authority。不同 placement
  保持竞争；不按强度、距离、holder center、总分或样片规则挑 winner。Contact、overlap、多异常和
  authority 不足继续 review。
- Placement 不再拥有检测角度：sequence 只解决长轴 phase/pitch，cross 只解决短轴 offset、fixed H
  和局部证据闭合。Aperture 边界保持 source-axis；局部 slope 只扩大输出保护，直接 enclosing pair
  才保留自己的 same-state slope。`APERTURE_PAIR` 和总高度不超过 `1.1H` 的
  `ENCLOSING_SUPPORT_PAIR` 互斥。
- 安全层只处理唯一 selected placement 的联合可行状态。Aperture 四边完整 expansion 各自使用 5%
  上限；enclosing top/bottom 使用 `1.1H` 合同。完整 pixel-center span 被纳入最终 footprint；真正所需
  polygon 越界时 review，不静默裁小。
- 二维内容只在最终 post-residual、post-bleed polygon 上作 negative veto。画面落在 nominal frame
  外但仍在 bleed 内可以通过；只有越过最终 crop 才否决。Content 不能移动边界、选择 runner 或创造
  phase。

### 输出与报告

- Deskew 降为 Decision 后的非阻断输出整理。只有 `approved_auto` 才执行 6–24 trace 的 role-free
  观测；不可用时保持原始倾斜，`needs_review` 直接记录 `output_not_eligible`。Deskew 不参与
  placement、Gate 或黄金准确性。
- Finalization 用同一个 affine transform 映射 source 与安全 polygon，再取精确半开 AABB；不得旋转
  后继续裁固定 W×H。AABB 在 polygon 外的角落允许为黑色 no-data。
- Current report 为 `x5crop_v5_template_report_11`。它保存最终 deskew assessment，不重复保存旁路
  observation；official footprints、transforms 和 final boxes 只对 approved output 暴露。
- 正式 TIFF 保留冻结输入域内的 16-bit RGB、ICC、resolution、metadata 和无损压缩，输出
  `Orientation=1`。全组先写 staging，全部成功后发布到尚不存在的目录。

### 实现与工具

- Registered gray 直接从 uint16 RGB 分块计算，复用两个 float32 luma plane 和一个 float64
  normalization plane；逐像素结果保持不变。普通 product path 在 report facts 冻结后、TIFF
  sampling 前释放整张 registered gray；development CLI 也在冻结完整 facts 后释放，只有 Debug
  Analysis 为画图保留。
- Final geometry、Gate facts 和 report record 由 canonical owner 直接导出，不再复制候选状态或使用
  单字段 wrapper。无消费者的 `RuntimeMetrics` 已删除；工作量与时间分别由 report 和 performance
  receipt 拥有。测试删除旧文件名、旧 schema 和任意模块行数上限等历史墓碑；物理反例合同保留。
- Performance receipt 为 `x5crop_performance_receipt_v5_5`：完整用户路径外部记录未插桩 peak RSS，
  cProfile 另行归因 `unattributed runtime`、decode、gray、coarse、measurement、alignment/decision、
  output deskew、sampling、write/readback 与 publish。派生 I/O 总时长不在每个 source 重复保存。
- 5 秒 mean 是正式性能 Gate；3 秒 mean 是记录明确但不阻断的 challenge。默认 `--jobs 1`、上限 3，
  内部数值线程固定为 1。
- `tools/verify` 是唯一验证入口。GitHub CI 不跳过 Markdown commit；本地 pre-push 仍按实际 commit
  range 选择 documentation 或 full。
- Performance、platform 和 release receipt 只证明绑定的 commit、依赖、机器与 cohort。已存在但
  无效的 performance receipt 会直接失败，不再由 platform 流程静默重建。
- Release contract 实际构建临时 ZIP，验证唯一 manifest、standalone source、LF bytes 和启动 smoke；
  用户包不包含 modular source、tests、tools、内部文档或开发输出。
- Measurement replay 和 v4.2.8 对照仅为绑定 identity 的开发工具，不携带真值、不进入 production，
  也不构成兼容路径。

### 验证边界

- 用户确认黄金决定几何准确性；nominal 必须安全自动批准，challenge 允许安全 review。
- 111-source diagnostic 只证明终态、schema、authority、工作量和 TIFF 工程合同，不产生准确率 verdict。
- Apple Silicon macOS、Intel macOS 与 Windows x64 必须在同一最终 commit 取得实机 receipt；没有独立
  卷时 exFAT 保持 `best_effort_unverified`。
- Accuracy、性能与三平台 receipt 全部绑定同一 release commit 前，不创建 RC、tag、Release 或公开 ZIP。

## V4.9（架构实验，不发布）

V4.9 建立 fixed-format template-first、source geometry、两级 Gate 与 source-coordinate safety，但
没有完成黄金 accuracy。它只存在于 Git history，不维护兼容路径。

## v4.2.8（当前稳定发布）

v4.2.8 证明了“先看整条片带，再在理论位置附近找 outer 和 separator”的行为可以快速覆盖规则片条。
V5 继承理论 pitch、material band、有限局部搜索、缺边投影和正常快车道；不恢复旧 confidence、
best-score、Grid 自证、content equal-split、固定像素 bleed 或 separator-center crop。

## 回滚

恢复历史版本时必须整体使用同一 commit 的 detector、configuration、schema、tests 与文档，不能跨版本
拼接组件。
