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
- 同一 source SHA 可保留多个显式 count 的独立测试任务并复用一份物理边界标注；cohort 只要求同源
  format 一致以及同一 task 的 format/count 不矛盾，不再错误地把 count 绑定到 source SHA。
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
- 直接绑定的 sequence start/end 直线仍不旋转 placement 或提供 phase，但其 fit line 若在当前 frame
  短轴 support 上超出已有 full position interval，超出的向外部分会进入 selected-placement 安全包络；
  已由 full interval 覆盖的 residual 不重复相加。这个合同覆盖 S098 一类实际分隔边不垂直的老化扫描。
- 安全层只处理唯一 selected placement 的联合可行状态。Aperture 四边完整 expansion 各自使用 5%
  上限；enclosing top/bottom 使用 `1.1H` 合同。完整 pixel-center span 被纳入最终 footprint；真正所需
  polygon 越界时 review，不静默裁小。
- 二维内容只在最终 post-residual、post-bleed polygon 上作 negative veto。画面落在 nominal frame
  外但仍在 bleed 内可以通过；只有越过最终 crop 才否决。Content 不能移动边界、选择 runner 或创造
  phase。

### 输出与报告

- Debug Analysis 第三联只用分帧颜色半透明填充实际最终 `OutputFootprint`，并保留同色实线边界；
  不再叠加 placement/feasible 范围或白色虚线框，review candidate 也不显示为正式输出。
- Deskew 降为 Decision 后的非阻断输出整理。只有 `approved_auto` 才执行 6–24 trace 的 role-free
  观测；不可用时保持原始倾斜，`needs_review` 直接记录 `output_not_eligible`。Deskew 不参与
  placement、Gate 或黄金准确性。默认 `--deskew auto`，也可用 `--deskew off` 明确保留原始方向。
  Observation 补齐 v4.2.8 的 100 px outer 和每 trace `max(10 px, 5% short extent)`；finalization
  继承 `0.03°` 和动态最小端点位移。V5 仍要求双侧稳定，并只应用不超过 `0.35°` 且端点位移不超过
  120 px 的小整理。超限记录 `rotation_exceeds_cleanup_limit`，不改变批准状态。
- Finalization 用同一个 affine transform 映射 source 与安全 polygon，再取精确半开 AABB；不得旋转
  后继续裁固定 W×H。AABB 在 polygon 外的角落允许为黑色 no-data。
- Current report 为 `x5crop_v5_template_report_12`。它只保存一次 holder/count/output-slot identity、
  每格 `OutputFootprint` 内的 sampling authority 和 source-wide deskew transform；静态架构声明、
  逐 slot 同义 transform/authority tuple 与旁路 observation 已删除。
- 正式 TIFF 保留冻结输入域内的 16-bit RGB、ICC、resolution、metadata 和无损压缩，输出
  `Orientation=1`。全组先写 staging，全部成功后发布到尚不存在的目录。

### 实现与工具

- 新增 source-SHA-bound 本地黄金标注器：按 SHA 去重物理边界，以共享短轴边、source-level
  `boundary_pool` 和每个显式 count 的 `slots`/`adjacencies` 表达多任务；contact 复用一条物理线，
  overlap 保留交叉边，空片、残缺曝光与源截断保留 typed slot 语义；支持 Orientation 1–8 可逆显示、
  有界总览、单张原 TIFF 的 1:1 局部检查、拖线/端点/逐像素微调、原子自动保存与最终确认冻结。
  1:1 局部图叠加当前任务的全部机器/人工边界，并在常规窗口中以约 512×512 的检查区呈现；
  选中线使用黄色前景与深色轮廓保持明暗背景可见；键盘 `[` / `]` 可绕整线中点或选中端点精细
  旋转。完整高度审阅按当前位置两条共享边计算短轴 H，让 H 占浏览器可用交叉轴约 94%；源 TIFF
  区域按屏幕尺寸缩小，点击只沿胶片长轴移动，短轴自动保持在共享边中间。该模式不改变常规 1:1
  检查，也不放大有界总览 JPG。
  独立像素拟合和旧红线草稿只生成 proposal，确认不会自动晋升 tracked accuracy cohort，工具及本地
  状态均不进入发布包。
- v2 红线批量恢复按用户声明区分已标注与未标注副本，并保存逐线 review basis。完整红线组按物理顺序
  对齐，不让错误机器 phase 覆盖人工线；缺线继续显示机器补线。会让照片离开 TIFF 栅格的红色共享边
  不被伪装成有效真值，而是保留对应机器 proposal 并要求原生像素审核。同源多 count 映射中，只有
  未被任何 task 使用的红线才产生 unresolved；被另一 count 使用的线只作为当前 task 的 inactive 映射事实。
- 黄金 accuracy 统一为单向最内侧可接受裁切合同，适用于 v1、v2 及以后 baseline schema：人工红线
  不是内容边界 oracle 或 detector 唯一答案；candidate 与正式 footprint 均不得向红线内侧越界，每侧
  向外安全包络受对应确认 span 的 5% 上限约束。删除了角点向内切的内容采样例外，
  `enclosing_support_pair` 也不能用 `1.1H` 总 span 掩盖单侧过度外扩；cohort 字段由
  `geometry_oracle_schema` 改为 `acceptance_contract` 与 `acceptance_baseline_schema`。
- Registered gray 直接从 uint16 RGB 分块计算，复用两个 float32 luma plane 和一个 float64
  normalization plane；逐像素结果保持不变。普通 product path 在 report facts 冻结后、TIFF
  sampling 前释放整张 registered gray；development CLI 也在冻结完整 facts 后释放，只有 Debug
  Analysis 为画图保留。
- Affine sampler 直接拥有 contiguous crop buffer，writer 在分配下一格前释放上一格；vertical deskew
  与 registered interval 分别使用 transpose/slice view，transition-line cache 在每个 source 后清空。
  这些变更不改变检测 observation、placement、Gate、footprint 或 TIFF 像素。
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
- 删除无现场消费者、无 verifier 入口的 measurement replay 与 v4.2.8 对照框架；历史行为留在 Git，
  九张用户确认黄金继续是唯一 accuracy reference。
- 删除一次性 measurement input/compile receipt、恒真 configuration 子 CLI、固定 report capability
  自述、无调用 convex clipping 与 production `__all__`。外部 report validator 移到 regression 工具层，
  不再嵌入 standalone；不为旧字段保留 alias、shim 或第二 schema。

### 验证边界

- 用户确认黄金按单向最内侧可接受裁切合同决定几何准确性；nominal 必须安全自动批准，challenge 允许
  安全 review。
- 受跟踪的 diagnostic cohort 只证明终态、schema、authority、工作量和 TIFF 工程合同，不产生准确率 verdict。
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
