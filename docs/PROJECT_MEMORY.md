# 项目记忆

更新：2026-07-30

这是 X5 Crop 唯一跨会话检查点。它只保存当前状态、验证边界、开放风险和下一步；当前
源码、Git、原 TIFF、current report、Debug Analysis 与现场命令输出始终优先。运行合同见
[ARCHITECTURE.md](ARCHITECTURE.md)，版本历史见 [CHANGELOG.md](CHANGELOG.md)。

## 当前目标

- 已批准下一原子切换：partial `auto` 不再推断真实照片 count，而是输出唯一匹配片夹对
  当前 format 的全部有效 slots；额外 blank 与完全空片的空白输出均可接受。
- 本次只同步决策与证据，不修改 runtime。另一个任务会基于本检查点写出原子实施计划，
  随后回到当前任务审核；计划审核通过前不开始新的代码切换。

## 当前状态

- 当前开发版为 V4.9；稳定公开 Release 仍为 `v4.2.8`。
- Runtime 已原子切换到 `bounded_safe_crop_grid`，不存在旧 schema reader、feature flag、
  fallback、compatibility shim 或第二套 detector。
- 用户提供 format。Full 使用 `fixed_full`；partial 支持 authoritative `explicit` count 与
  bounded `auto` count。当前 `main@7478ca09` 的 auto 仍搜索有限 count 集并执行跨 count
  dominance；它尚未实现已批准的容量输出语义。
- `CandidateGate` 只记录十项候选安全事实；只有 `DecisionGate` 创建
  `approved_auto`、`needs_review` 与 typed reasons。
- Approved 输出在 DecisionGate 后冻结 count、transform 与 boxes；每个 ROI 只从原图采样
  一次，写出后复读验证 TIFF pixels、dtype、axes/channels、ICC、resolution、metadata 与
  NONE/LZW 无损压缩行为。
- I/O 失败保持独立 `FailedInput` / terminal failure，不转换成 review。
- Sparse checkout 已关闭；所有受跟踪文件均保存在本地。
- 实质性文档集中在 `docs/`。根目录只保留 GitHub/工具自动发现所需的 `README.md`、
  `AGENTS.md`、`LICENSE` 与运行入口。
- Installer 模板位于 `tools/install/`；release manifest 将它们映射到用户 ZIP 的
  `install/`。发布包同时包含 `LICENSE`。

## 不可偏移的产品合同

- 成功标准是不内切真实照片内容，而不是唯一恢复物理边界或复刻历史 boxes。
- Full 使用固定 count；partial `explicit` 严格服从用户 count。Partial `auto` 在唯一匹配
  scan-canvas 后只使用该片夹的有效最大容量作为 `output_slot_count`，不推断或宣称真实
  照片张数。
- `approved_auto` 允许向外多保留、相邻输出重叠、blank slot、inferred Grid、
  protection saturation，以及 bounded shared pixels；额外空白 TIFF 和完全空片的全部
  空白 slots 均可接受。
- `needs_review` 只用于 protection 无法吸收的同一容量 Grid ordinal/placement、primary
  ownership、containment、source/lane authority 或 output geometry 风险。跨 count
  竞争在容量输出模型中不存在。
- Separator 缺失、等价 geometry、未 deskew 或邻片像素本身不能制造 review。
- Format、scan-canvas、scale、source content、separator、Grid、protection、Gate、
  finalization、output 与 report 各有唯一 owner，权限只向下游流动。
- Filename count/`pass`/`unknown` 只属于 validation cohort，永不进入 detector、prior、
  score、Gate 或 runtime selection。

## 当前验证边界

- Tracked synthetic contracts 覆盖 count mapping、scan-canvas capacity、source
  measurement、separator owner、bounded Grid、dominance、slot/interaction/envelope、
  Gate、TIFF、report、performance schema、release package 与 current-only 清理。
  其中跨 count dominance 属于待原子删除的 current contract，不得带入容量输出方案。
- Accuracy completion 只使用 9 张 source-SHA-bound、用户确认 geometry 的黄金样片，
  展开为 14 个 fixed/explicit/auto 场景。
- 111 条 manifest 只作非阻断 coverage audit；重复 SHA 必须单列，record 数不能称为
  独立真实样片数。
- `real_holdout = unavailable`。XPan、120-645 等没有真实样片的 cell 保持
  `real_sample_coverage = unavailable`，但 coverage gap 不制造 review。
- 正式性能合同是固定 24 张、`--jobs 2`、一个空 root 下的 `cold` 与
  `measured-1/2/3`；四次均真实写出并复读，认证只取三次 measured 中位数并要求
  `<= 5.0 秒/张`。
- Acceptance、111 audit 与性能结果是运行产物，不在 tracked tree 冒充永久真值；发布前
  必须针对 current HEAD 重新生成并人工检查。

## 2026-07-30 只读决策证据

- `main@7478ca09` 工作树干净；current 黄金 acceptance 为 14/14。
- 111 条 coverage audit 完成 111/111：110 条 `approved_auto`、1 条
  `needs_review`。88 条 `pass_*` 已全部批准，因此当前主要问题不是 review 率。
- 51 条 partial 的 current count 关系为 25 exact、3 over、22 under、1 unresolved；
  其中 41 条 pass partial 为 22 exact、2 over、17 under。Filename count 只作
  validation annotation，未进入 runtime。
- S067 的非权威 Debug 诊断显示三张可见照片时 auto 只输出 1 个中间 ROI；explicit 3
  输出三张。该检查只证明现有 count policy 的风险，不建立或改写 baseline。
- 使用 current explicit 单-count 路径请求这些样片的 format 最大容量（与其匹配片夹容量
  相同）的模拟中，51/51 条 partial 均批准且没有低于 annotation。五张 partial 黄金样片
  的所有确认 polygons 均被
  source-order 一对一包含：S051 映射到 6 个 slots 的 1–3，S055 为 1–4，S062/S091
  为 1–3，S109 为 12 个 slots 的 6–12。
- 固定 24 张性能 cohort 若全部按容量输出，静态 frame 数由 139 增至 168（+29，约
  21%）。搜索工作会下降，但没有 current runtime 的正式性能 receipt，不能提前声明
  `<= 5.0 秒/张` 仍成立。

## 本地样片与证据

- `Test/` 是 ignored 的本地验收样片库，保留原 TIFF、111-source manifest、九张黄金样片
  的 source/marked/review/baseline 证据及必要 symlink。
- `Test/` 不属于源码、Release 或 verifier 的目录布局合同。验收 runner 只消费 tracked
  cohort 与 manifest canonical current records，不盲扫文件名。
- 已被当前实现取代的 source-core prototype、旧 cutover receipt 与旧生成报告不再是
  runtime 或验证输入；其结论只保留在 Git history 与更新日志。

## 开放风险与下一步

- V4.9 尚未创建新的 GitHub Release；普通用户下载仍以 `v4.2.8` 为准。
- XPan、120-645 与部分 format/mode/count/placement/interaction 仍缺真实样片覆盖。
- 下一任务只写实施计划，不直接复用此前的“跨 count safe-coverage”方案。计划必须从
  unique scan-canvas fit 解析单一 `output_slot_count`，删除跨 count search/dominance、
  competition/reason/report/contracts，并保留同一容量 count 内的 Grid、ownership、
  containment、protection、CandidateGate 与 DecisionGate。
- 计划必须原子更新 current schema：fixed/explicit 精确 count；auto 精确等于有效片夹
  容量；黄金 partial 使用 source-order 一对一 containment，不按相同 ordinal 强行配对；
  51 条 partial annotation 只作 approved output 的 validation lower bound。
- 计划还必须覆盖公共中英文文档的同批切换、24 张真实 TIFF 性能复测、extra-slot
  统计、111 coverage、人工 output/report/Debug 检查和 standalone package；不得把搜索
  降低当作 I/O 性能证明。
- 当前任务的下一步是审核另一任务写出的原子计划，重点检查是否误保留跨 count
  abstraction、是否把容量 count 当真实 count、是否绕过 Gate，以及是否低估额外 TIFF 的
  I/O 与用户体验成本。
- 若上述运行暴露 named physical gap，只补该 gap 所需的 measurement、contract 或真实
  样片；不得恢复旧 detector/schema、样片 whitelist 或更严格的 proof-only approve
  标准。
