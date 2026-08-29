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
  outer、separator 与 top/bottom 邻域一次测量。固定 W/H 与 typed evidence 决定 phase、pitch、cross、
  ordinal 和最多一次直接 local advance；像素强度、片夹中心或样片规则不能替代 authority。
- 任一 slot 不安全时整张 source `needs_review`，不做 slot salvage。Contact 与 overlap 始终属于
  challenge；安全 review 是合格结果，不启用第二套 detector 或特殊 bleed。
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
  阻断原因；不重新求解，也不把 review candidate 伪装为正式输出。
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
- Nominal/challenge 在 detector 运行前由人工证据和固定模板合同逐 task 派生，并随确认基线冻结；
  accuracy 会重新推导核对，不能手填改类。Nominal 必须安全自动批准，challenge 允许安全 review。
- 两侧各空余至少一个固定 W、又缺少双端直接 outer 的内部 partial sequence 属于 challenge；该角色只从
  确认前几何推导，不由当前 detector 的结果或 post-selection holder fill 决定。
- Accuracy 只接受当前确认 task。没有当前 blocking cohort 时明确报告
  `calibration is incomplete`，不回退历史基线。空 slot 不参与几何比较，但 runtime 对应输出与 ordinal
  必须保留。
- 完整确认集合通过唯一生成器独立核对 source、确认快照、审阅 artifact、task authority、角色和 geometry
  digest 后，才写入 tracked blocking cohort。Development-only 黄金分析把基础 nominal、较难 nominal 与
  challenge 分开，并逐边区分已观察且绑定、已观察未绑定、模板补全和竞争状态；这些诊断不进入 runtime
  或黄金权限。

### 工程与验证

- `tifffile + imagecodecs` 独占正式 TIFF I/O；OpenCV 只作有界像素测量，SciPy 只作数值与 sampling，
  Pillow 只在 Debug Analysis 延迟导入。生产默认 `--jobs 1`、上限 3，内部数值线程固定为 1。
- Registered gray、affine crop buffer 与 source-local cache 按阶段释放；这些优化不得改变 observation、
  placement、Gate、footprint 或输出像素。
- `tools/verify` 是 Hook、CI 与本地验证的唯一入口。Diagnostic 只证明工程合同；gold accuracy、性能与
  platform receipt 分层记录，不互相冒充。
- 正式性能 Gate 为 24-source 完整用户路径 mean 不超过 5 秒；3 秒只是不阻断的 challenge。
- Apple Silicon macOS、Intel macOS 与 Windows x64 必须在同一最终 commit 取得实机 receipt。Accuracy、
  性能与平台证据未全部绑定该 commit 前，不创建 RC、tag、Release 或公开 ZIP。
- 发布包由唯一 manifest 构建，不包含 modular source、tests、tools、内部文档或开发输出。

## V4.9（架构实验，不发布）

V4.9 建立 fixed-format template-first、source geometry、两级 Gate 与 source-coordinate safety，但没有
完成黄金 accuracy。它只存在于 Git history，不维护兼容路径。

## v4.2.8（当前稳定发布）

v4.2.8 证明“先看整条片带，再在理论位置附近找 outer 和 separator”可以快速覆盖规则片条。V5 继承
理论 pitch、material band、有限局部搜索与缺边投影，不恢复旧 confidence、best-score、Grid 自证、
content equal-split、固定像素 bleed 或 separator-center crop。

## 回滚

恢复历史版本必须整体使用同一 commit 的 detector、configuration、schema、tests 与文档，不能跨版本
拼接组件。
