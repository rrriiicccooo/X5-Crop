# X5 Crop 更新日志

本文件只记录版本级行为、验证边界与必要回滚背景。当前源码结构见
[ARCHITECTURE.md](ARCHITECTURE.md)。

## V5（下一生产目标，尚未实现）

V5 是下一条 current-only 生产实现。它继承 V4.9 已验证的 template-first、联合 source
geometry、retained placements、安全包络、逐边 5%/3%、两个 Gate 与 lane-safe TIFF 合同；
像素测量和数值层可改用 OpenCV、SciPy 等成熟依赖。

本节只记录版本方向。V5 尚无 runtime、schema、accuracy、性能或发布完成声明。

验证按 pushed paths 分级：纯 Markdown 只检查文档 diff，非 runtime 代码运行 full contracts，
只有 runtime、依赖或固定性能输入变化才要求 performance receipts。

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
