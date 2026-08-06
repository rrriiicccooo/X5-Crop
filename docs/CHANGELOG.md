# X5 Crop 更新日志

本文件只记录版本级行为、验证边界与必要回滚背景。当前源码结构见
[ARCHITECTURE.md](ARCHITECTURE.md)。

## V5（下一生产目标，尚未实现）

V5 是下一条 current-only 生产实现。它继承 V4.9 已验证的 template-first、联合 source
geometry、retained placements、安全包络、逐边 5%/3%、两个 Gate 与 lane-safe TIFF 合同；
像素测量和数值层可改用 OpenCV、SciPy 等成熟依赖。

V5 的目标输入是 format、mode 与必要 count 已知的 X5 片夹扫描。每个 lane 保持明确顺序，
支持水平、垂直、TIFF Orientation，以及相邻照片接触或局部重叠；不处理两段胶片物理压叠。
Decision 继续以整个 source 为原子，不输出部分成功 slots。Deskew 只校正共同 top/bottom 长边，
不做 projective 或非线性变形。Blank TIFF suppression 不属于 V5 完成目标。

生产依赖将冻结版本并安装到用户级 Python site，使 standalone script 可放在任意文件夹；
macOS 与 Windows 使用同一核心合同并分别验证安装、启动、TIFF I/O 与性能。V5 性能以完整用户
路径计时，多尺度 evidence 只在预登记的有界区域内计算，X5 Crop 独占 source 并发。

V5 使用全部用户确认黄金进行开发与回归，不建立独立 holdout。S055、S098 为 challenge，
其余为 nominal；challenge 可以安全 review，但不安全批准始终失败。弱边、接触/重叠、空槽与
Orientation 样片可在人工确认后继续加入。135-dual 不增加真实样片，XPan 与 120-645 样片以后
补充，均不阻断通用实现。

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
