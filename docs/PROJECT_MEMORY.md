# 项目记忆

更新：2026-08-06

这是唯一跨会话检查点，只保存当前目标、已验证检查点、开放风险与精确下一步。当前架构见
[ARCHITECTURE.md](ARCHITECTURE.md)，版本变化见 [CHANGELOG.md](CHANGELOG.md)。源码、Git、
原 TIFF、current report、Debug Analysis 与现场命令输出始终优先。

## 当前目标

V4.9 已完成 template-first 架构实验使命，不再作为发布目标，也不再要求先修到黄金样片全部
通过。下一生产版本是 V5，直接在 `main` 上 current-only 实现，不创建 V5 开发分支。

V5 使用真正适合生产的像素与数值依赖实现项目目标：不切掉真实内容，同时提高识别覆盖、
边界准确率、安全自动批准率与速度。达到正确性下限后，deskew 优化排在速度之后。Blank TIFF
suppression 不属于 V5 完成目标，只保留为未来版本独立重新定义的方向。

## V5 冻结方向

- 保留 format/count authority、template-first、source-wide joint geometry、NominalPitch、
  LocalAdvanceRelation、retained placements、MaximumLegalWindow、逐边 5%/3% 与两个 Gate。
- `tifffile + imagecodecs` 独占原 TIFF 解码和写出；NumPy 是统一数据层；OpenCV 只提供有界
  像素测量；SciPy 只提供峰值、拟合、区间与采样等数值原语；Pillow 只服务 Debug Analysis。
- Producer 不恢复 local-line 排名、通用 DP、top-K、width×height 笛卡尔积、逐帧 scale 或
  Hough line-family authority。分数只能选择 canonical，不能删除会改变安全 union 或 legal-
  window intersection 的完整摆放。
- 安全输出必须包含全部 retained full footprints，并位于全部 retained physical
  interpretations 的合法窗口交集内。Canonical 只负责代表 geometry、deskew、minimum guard
  与报告。
- V5 只处理 format、mode 与必要 count 已知的 X5 片夹扫描。每个 lane 是顺序明确的一条片条；
  支持水平、垂直、TIFF Orientation，以及相邻照片接触或局部重叠，不处理两段胶片物理压叠。
- Decision 以整个 source 为原子；任一 slot 无法安全成立时整张 `needs_review`，正式 TIFF 为
  零。V5 不建立 slot salvage 或部分输出。
- TIFF decode 建立 raw raster 到 canonical visual coordinates 的可逆 Orientation 映射；检测、
  ordinal 与输出使用 canonical coordinates，正式输出写 `Orientation=1`。
- Deskew 只把共同 top/bottom 长边校正为水平；每 lane 一个共享方向、一次 inverse-affine
  sampling，不要求短边垂直，也不做 projective 或非线性变形。
- V5 从首个端到端 vertical slice 开始使用 source-SHA-bound 黄金 geometry；只修通用算法，
  不增加样片规则、whitelist 或放宽安全预算。
- S055、S098 是 challenge，其余七张是 nominal。全部黄金都可用于开发与回归，不建立独立
  holdout，也不把结果表述为未知总体上的独立泛化率。Nominal 必须安全批准；challenge 可以
  安全 review，但任何不安全批准都失败。弱边、接触/重叠、空槽与 Orientation 黄金以后按
  source-SHA-bound 人工确认流程增加。
- 当前所有 capacity slots 都按可能含照片处理并继续输出。V5 不建立 blank producer、
  occupancy Gate 或 suppression schema。
- 生产依赖按 Release 冻结并安装到用户级 Python site，不创建私有 `.venv`，使 standalone
  script 可在任意文件夹运行。X5 Crop 独占 source 并发，OpenCV、BLAS、OpenMP 与 SciPy 内部
  线程默认固定为 1；多尺度 evidence 只在预登记区域分块计算。
- macOS 与 Windows 都是正式平台；核心合同相同，但 Release Candidate 仍分别验证安装器、
  启动器、依赖版本、代表性黄金、TIFF I/O 与性能下限。
- 验证按 pushed paths 分级：纯 Markdown 只检查文档 diff；工具、测试、Hook 与发布配置运行
  full contracts；runtime、依赖或固定性能输入变化才要求 performance receipts。

## 已验证检查点

- Pre-V5 架构 checkpoint 为 `8c8040b0`；V4.9 current-only 替换已推送，旧 producer 与兼容路径
  已删除。
- 非黄金验证通过 81 个 current contracts、13 个配置 format/mode pairs、168-task 固定
  workload、compileall 与 standalone version。
- 111-source 工程诊断完成 111/111 terminal records，runtime、authority、query/template、内存
  与正式 TIFF failure 均为零；accuracy 明确为 `not_assessed`。
- 固定 S062 与 24-source/168-task 性能 receipts、代表性 Debug、中文路径、ZIP manifest、UTF-8
  文件名、CRC 复读与 lane-safe sampling 已通过实验检查点验证。

## 验证边界与开放风险

- 当前源码仍是 V4.9 实验实现；V5 dependency、runtime、schema、黄金 comparator 与发布包均未
  建立。
- V4.9 未读取黄金 accuracy cohort，不能证明真实 detection、placement survival、containment、
  自动批准率或 deskew；这些验证直接转入 V5。
- OpenCV/SciPy 必须带来可测量的准确率、批准率、速度或 deskew 收益，不能只增加包体、启动
  成本或第二套 owner。
- 任何通过丢弃有效竞争、放宽 5%/3%、增加样片阈值、扩大 review 或破坏 TIFF 保真换来的通过
  都无效。
- Deskew 的最终用户门槛尚未冻结；第一条可运行 slice 后，以单张照片宽度上的 top/bottom
  最大垂直漂移生成数值与视觉对比，再由用户一次确认。
- 现有样片足以开发 V5。135-dual 不增加真实样片；XPan 与 120-645 样片以后加入，不阻断当前
  实现，也不产生格式 denylist。原 TIFF 与人工黄金资产已有 Git 外备份，无需提交 Git。

## 精确下一步

1. 第一批 V5 runtime 变更同时建立唯一 schema、黄金 comparator、端到端 performance receipt、
   冻结 dependency identity，并删除同批被替代的 V4.9 实现。
2. 完成 TIFF decode/Orientation → registered bounded measurement → template placement → source-
   atomic safe output → TIFF readback 的端到端 vertical slice。
3. 从第一条 slice 起运行全部黄金，验证 observation、placement survival、containment、逐边
   5%/3%、批准与 deskew；随后按 source-SHA-bound 人工确认增加困难 challenge 样片。
4. 输出 deskew 后单张照片宽度上的 top/bottom 最大垂直漂移与视觉对比，由用户冻结门槛。
5. 按完整用户路径性能和有界内存证据扩展全部 format/mode，最后在 macOS、Windows 分别完成
   Release Candidate 验证。V5 不实施 blank TIFF suppression。
