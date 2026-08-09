# X5 Crop 更新日志

本文件只记录版本级行为与验证边界。当前系统见
[ARCHITECTURE.md](ARCHITECTURE.md)，当前任务见按需读取的
[PROJECT_MEMORY.md](PROJECT_MEMORY.md)。

## V5（当前开发版本，尚未发布）

V5 已以 current-only 方式替换 V4.9 active runtime。源码、CLI、schema、tests、tools 与
standalone 只消费当前 owner，不保留 fallback、shim、feature flag 或旧 schema reader。公开
稳定版本仍为 `v4.2.8`。

### 产品行为

- 输入冻结为单页 16-bit RGB contiguous TIFF 与受支持的无损压缩。Orientation 1–8 在 decode
  boundary 转为 canonical coordinates，正式输出写 `Orientation=1`。
- Detector 使用 registered measurement、template-first grouping、联合 scale、retained complete
  placements 与分项 safety uncertainty。历史版本中有效的多 trace profile、opposite-polarity
  edge pair、registered rebind 和 local-advance refinement 已回收到同一有界路径；未恢复通用
  DP、top-K、候选笛卡尔积或 best-score authority。
- `CandidateGate` 只记录 typed assessment，`DecisionGate` 独占 final status 与 reasons。任一
  slot 无法 containment、超出 legal window 或逐边 5%/3% direct-use budget 时，整个 source
  `needs_review`，不做 slot salvage。
- 每个 lane 共享 top/bottom 方向并只执行一次分块 SciPy inverse-affine sampling。输出 TIFF
  关闭后复读验证 pixels、结构、ICC、resolution、metadata、压缩与 Orientation。
- 照片直接位于 `x5_crop_output/` 根部。新结果在同父目录完整构建后通过 lock、journal 和两次
  rename 发布；旧结果只有 owner marker、current manifest 与 inventory 全部一致时才删除。
  单 source `runtime_error` 不取消其它结果；全部失败不发布。
- 普通运行不计算 source-content SHA，不加载 Git、cohort、comparator、profiling、receipt 或
  fault injection。Pillow 只在显式 Debug Analysis 时延迟导入。
- 依赖安装改为 provider-neutral 的模块能力合同：可用项零改动复用，缺失项最小安装，版本不符
  只沿确认的 pip 或 Homebrew owner 更新，未知 ownership 在写入前停止。
- 正式 CLI 删除 `--overwrite` 与旧 debug/diagnostic flags。生产默认 `--jobs 1`、上限 3；数值
  库内部线程固定为 1。
- Debug Analysis 使用 source-aspect 自适应三联图，分别呈现 TOP/BOTTOM、START/END 和最终
  safety/output。它只读取 current report facts，不重新计算检测、geometry 或 budget。

### 验证与发布边界

- 唯一入口为
  `tools/verify staged|full|accuracy|diagnostic|performance|platform|platform-check|platform-package|pre-push`。
  CI 在 Ubuntu、Windows、Apple Silicon macOS 与 Intel macOS 上覆盖 Python 3.12–3.14。
- Accuracy 使用九张 source-SHA-bound 黄金的十四项正式 CLI 任务；111-source diagnostic 只作
  工程合同；24-source performance 分离正式用户路径 Gate 与外部 profiling。
- Platform receipt schema 为 `x5crop_platform_receipt_v2`，绑定当前 `full`、真实平台 I/O、
  文件系统、安装器和 performance receipt。已经结束的 non-detection 阶段 freeze 不再进入平台
  证据，也不保留独立 verifier。
- 验证工具、CI 或旧 receipt 均不构成 V5 发布声明。只有黄金、性能和目标平台实机证据全部绑定
  同一 release commit 后，才可创建 RC、tag、GitHub Release 或公开 ZIP。

## V4.9（架构实验，不发布）

V4.9 完成 fixed-format template-first、联合 source geometry、两级 Gate、source-coordinate
safety 与单次 affine writer 的结构实验，但没有完成黄金 accuracy。它只作为 V5 的历史背景，
不再维护、打包或恢复兼容路径。

## v4.2.8（当前稳定发布）

v4.2.8 使用一维 profile、理论节距附近搜索、basic 优先和 enhanced 按需，取得良好速度与多数
场景的实用裁切。其 confidence、固定 bleed、format thresholds 与 best-score selection 不是
V5 的安全 authority。

## 回滚

恢复历史版本时必须整体使用同一 Git commit 的 detector、configuration、schema、tests 与
文档，不能跨版本拼接组件。
