# X5 Crop 更新日志

本文件只记录版本级行为、验证边界与必要回滚背景。当前源码结构见
[ARCHITECTURE.md](ARCHITECTURE.md)。

## V5（当前开发版本，尚未发布）

V5 已原子替换仓库中的 V4.9 active runtime。源码、CLI、report、manifest、tests、tools 与
standalone 只消费 current schema；不存在 V4.9 fallback、shim、feature flag 或旧 schema reader。
当前公开稳定版本仍为 v4.2.8，本节不构成 V5 发布声明。

已实现的版本行为：

- 严格单页 16-bit RGB contiguous TIFF 输入域；`tifffile + imagecodecs` 独占正式 I/O，
  Orientation 1–8 在 decode boundary 转为 canonical coordinates，输出固定为 Orientation=1。
- Registered transition 保存坐标区间、宽度、prominence、polarity、local noise、support、trace
  与 provenance；template-first producer 建立联合 scale、完整 placements、canonical 代表和
  retained safety union，不使用通用 DP、top-K 或候选笛卡尔积。
- 回收历史版本中仍符合 V5 authority 与性能合同的像素能力：多 trace/多分段 profile 聚合、
  opposite-polarity edge pair、片段内 registered transition 重绑定、photo-edge ridge 与 joint
  local-advance/scale refinement。聚合只在线性数量的 registered records 上运行，不恢复旧版
  confidence PASS、best-score、format threshold 堆、全图 content cache 或第二条 runtime。
- Robust center 与 safety uncertainty 已分离：fit angle 只服务共同方向的代表解，transition
  interval/width、fit residual 与数值误差进入 full angle hull；水平和垂直 lane 使用同一旋转符号
  合同。
- `CandidateGate` 只冻结 typed assessment，`DecisionGate` 独占 final status 与 reasons；任一
  slot 无法满足 containment、legal window 或逐边 5%/3% direct-use budget 时，整个 source
  `needs_review`。
- 每个 lane 共享 top/bottom 长边方向，只执行一次分块 SciPy inverse-affine sampling；每张正式
  TIFF 在关闭写句柄后复读验证像素、结构、ICC、resolution、metadata、压缩和 Orientation。
- 正式照片直接写入 `x5_crop_output/` 根部。新结果在同父目录完整构建后，通过 target-specific
  lock、journal 和两次 rename 发布；只有 current owner marker 与完整 inventory 可确认的旧结果
  才会删除。进程崩溃可恢复，断电歧义保留全部数据。
- 单个 source 的 detection、sampling、编码或复读失败只生成 `runtime_error` terminal，其他有效
  source 仍可发布；全部失败不发布。invocation scheduler 在 sampling 前统一检查新结果、旧结果、
  报告、debug、事务开销与 32 MiB guard 的空间。
- 普通运行不计算 source-content SHA，不加载 cohort、comparator、profiling、receipt、Git 或故障
  注入。Pillow 只在显式启用 Debug Analysis 时延迟导入。开发工具先在计时外核对 source SHA，
  再以子进程调用完全相同的正式 CLI。
- 依赖合同改为 provider-neutral 的模块能力合同。安装器逐项检查 fresh import、模块版本与真实
  ownership：可用项零改动复用，缺失项才安装 user-site binary wheel，版本不符项沿已确认的
  pip distribution 或 Homebrew formula 更新；未知 provider 在写入前停止。Homebrew 从来不是
  macOS 前置条件，OpenCV 也不再由 distribution metadata 是否存在决定“已安装/未安装”。
- OpenCV 内部线程先请求 1；若当前并发 backend 忽略该值，则改用 0 明确关闭内部并发，使
  不同 OpenCV provider 都保持实际单线程，source 级并发仍只由 `--jobs` 拥有。
- 正式 CLI 删除 `--overwrite`、`--diagnostics` 和旧 debug flags；未验证文件系统的非交互运行必须
  显式使用 `--allow-best-effort-output`，但该选择不能绕过锁、路径、rename 或空间硬失败。

验证拓扑已统一为 `tools/verify staged|full|accuracy|diagnostic|performance|pre-push`。`full`
只运行 CI 可获得的 contracts、合成 TIFF、schema、配置、standalone 与事务检查；`accuracy`
使用九张 source-SHA-bound 黄金的十四项正式 CLI 任务；`diagnostic` 以正式 CLI 运行 111 sources；
`performance` 在外部 SHA 核对后测量 24-source 完整用户路径并绑定 commit、依赖和 workload。

当前完成边界：合成 full contracts 已通过 127 项（1 项平台条件跳过）；九张黄金十四项中，
S027、S035、S091 explicit/auto 与 S094 已正式通过，S055 和 S098 保持安全送审，仍有六个
nominal 任务未达到冻结标准。111-source 工程诊断已达到 111/111，但
原先绑定 `4ca03877` 的 Apple Silicon receipt 使用临时 PyPI OpenCV overlay，其依赖身份已由
current-only provider-neutral 合同替代，不能继续作为当前 tree 的性能凭据。Windows x64、Intel
macOS 性能，以及三平台完整依赖安装、真实 TIFF、中文路径、文件占用与恢复验证仍未完成。
因此 V5 不是 release-ready，也不能宣布三平台正式支持。

## V4.9（架构实验，不发布）

V4.9 完成了破坏性的 current-only 架构实验，不再追求黄金样片全部通过或 release-ready。
它是 V5 的语义与结构基础，不是待发布候选。

### 实验结果

- 检测改为 fixed-format template-first：基础一维 profiles 形成完整模板 groups，再由整组像素
  证据确认 phase、pitch、local delta 与共同 direction。
- 同一 source 共享真实宽高和两个 axis scales；start/end 严格正交于共同 direction。
- 删除 local-line 排名、通用 DP、候选笛卡尔积、top-K、blank geometry 与旧兼容路径。
- `SafeCropEnvelope` 包含全部 retained footprints；输出同时受全部 physical legal windows
  约束，start/end 每边 5%，top/bottom 每边 3%。
- `CandidateGate` 只冻结 typed facts，`DecisionGate` 独占 final status 与 reasons。
- Writer 只从原 TIFF 执行一次 inverse-affine sampling，并逐 tap 遵守 lane authority。
- Current report 为 `source_coordinate_format_placement_v2`；Debug Analysis 只读取 current facts。

### 验证边界

V4.9 checkpoint 已通过 current contracts、配置组合、111-source 工程诊断、固定性能、Debug、
standalone 与 TIFF 复读。黄金 accuracy 未评估，因此它不证明真实识别准确率、自动批准率或
release-ready；没有创建 tag、GitHub Release 或公开 ZIP。

## v4.2.8（当前稳定发布）

v4.2.8 以一维 profile、理论节距附近搜索、basic 优先和 enhanced 按需获得良好速度与多数
场景的实用裁切。它使用 confidence、固定 bleed、format-specific thresholds 与 best-score
selection，不是 V5 的安全 authority。

## 回滚与发布

- 恢复任一历史版本时，必须整体使用同一 Git commit 的 detector、configuration、schema、
  tests 与 docs，不混用组件。
- 发布包使用 `python3 -m tools.release.build --version <version>` 构建。
- 只有 release-ready 验证完成后，才创建 tag、GitHub Release 与公开 ZIP。
