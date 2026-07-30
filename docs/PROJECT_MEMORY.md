# 项目记忆

更新：2026-07-30

这是 X5 Crop 唯一跨会话检查点。它只保存当前状态、验证边界、开放风险和下一步；当前
源码、Git、原 TIFF、current report、Debug Analysis 与现场命令输出始终优先。运行合同见
[ARCHITECTURE.md](ARCHITECTURE.md)，版本历史见 [CHANGELOG.md](CHANGELOG.md)。

## 当前状态

- 当前开发版为 V4.9；稳定公开 Release 仍为 `v4.2.8`。
- Runtime 已原子切换到 `bounded_safe_crop_grid`，不存在旧 schema reader、feature flag、
  fallback、compatibility shim 或第二套 detector。
- 用户提供 format。Full 使用 `fixed_full`；partial 支持 authoritative `explicit` count 与
  bounded `auto` count。
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
- `approved_auto` 允许向外多保留、相邻输出重叠、blank slot、inferred Grid、
  protection saturation，以及 bounded shared pixels。
- `needs_review` 只用于 protection 无法吸收的 count、ordinal、primary ownership、
  containment、source/lane authority 或 output geometry 风险。
- Separator 缺失、等价 geometry、未 deskew 或邻片像素本身不能制造 review。
- Format、scan-canvas、scale、source content、separator、Grid、protection、Gate、
  finalization、output 与 report 各有唯一 owner，权限只向下游流动。
- Filename count/`pass`/`unknown` 只属于 validation cohort，永不进入 detector、prior、
  score、Gate 或 runtime selection。

## 当前验证边界

- Tracked synthetic contracts 覆盖 count mapping、scan-canvas capacity、source
  measurement、separator owner、bounded Grid、dominance、slot/interaction/envelope、
  Gate、TIFF、report、performance schema、release package 与 current-only 清理。
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
- 发布 V4.9 前必须重新运行 focused contracts、14 场景、111 coverage audit、人工 TIFF/
  report/Debug 检查、固定 24 张正式性能和 standalone package 检查；随后通过 hooks
  commit/push，不在 push 前重复手工 full validation。
- 若上述运行暴露 named physical gap，只补该 gap 所需的 measurement、contract 或真实
  样片；不得恢复旧 detector/schema、样片 whitelist 或更严格的 proof-only approve
  标准。
