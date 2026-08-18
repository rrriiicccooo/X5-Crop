# 项目记忆

更新：2026-08-18

这是唯一跨会话检查点。长期政策见 [AGENTS.md](../AGENTS.md)，运行合同见
[ARCHITECTURE.md](ARCHITECTURE.md)，版本变化见 [CHANGELOG.md](CHANGELOG.md)。现场 Git、源码、
原 TIFF、current report、Debug Analysis 和最新命令输出优先。

## 当前目标

完成从上次推送以来全部讨论的一次 current-only 收口：把 v4.2.8 的 whole-to-local 优势与 V5 的固定
模板、独立证据、共享 deskew、单次局部位移、两种 cross boundary use、联合输出保护、typed Gate、
诊断和完整路径性能工具合成一条主线；验证后提交并推送 `main`。V5 尚未发布。

## 当前事实

- Runtime 输入已经是 format + 可选 count；没有 full/partial mode。135-dual 非 12 count 安全 review。
- Production path 是 bounded measurement plan → phase/pitch/local residual → cross/direction →
  fixed placement → selected-only joint footprint → final decision。
- Aperture 使用正常 bleed 与四边单边 5%；enclosing support 不加 cross bleed，并受总高度 1.1H
  限制。
- Contact/overlap 没有用户确认黄金，当前只产生 review。
- 当前完整工作树 fresh `tools/verify full` 通过：358 tests，skip 2；compile、配置、cohort、shell 与
  version contract 全部通过。
- 当前完整工作树 fresh 九张黄金全部安全：七张正确 `approved_auto`，S055、S098 两张 challenge
  安全 `needs_review`；没有错误自动通过，也没有 nominal 通过率回退。
- 当前完整工作树 fresh 111-source diagnostic 全部完成且工程合同通过：32 张自动批准、79 张
  review。当前阻止事实主要是 placement/phase/cross 唯一性 40、content veto 14、output footprint
  或 direct-use precision 18、local advance 5 和无完整 placement 2；该队列的 recognition accuracy
  仍为 `not_assessed`。
- 最近一次 clean-tree 24-source 完整路径性能通过：mean 约 3.5 秒/张，p50 约 2.9 秒，p95 约
  6.7 秒。阶段均值以 sampling 约 1.35 秒、startup/import 约 1.29 秒和 template
  alignment/decision 约 0.80 秒为主；coarse support 约 0.008 秒，TIFF I/O 合计约 0.28 秒。
  精确值与有效性只属于绑定 commit 的 performance receipt。
- 最近一次 Apple Silicon clean-tree platform I/O、APFS 与 HFS+ 本机验证通过；exFAT 按合同标记
  best-effort unverified。该证据不替代 Windows x64 或 Intel macOS 实机验证。

## 开放风险

- 当前性能平均值低于 5 秒上限约 1.4 秒，但 p95 和部分自动输出仍超过 5 秒；下一轮性能工作应
  优先看 sampling、startup 和 template alignment，而不是凭直觉先改 coarse pass 或 TIFF I/O。
- Diagnostic 没有真值；review 原因统计只决定改进优先级，不能证明或否定边界准确。
- Overlap 自动输出必须等待用户确认 overlap 黄金，不因发布版历史行为或“没有 band”提前开放。
- 目标平台 receipt 仍须在未来 release commit 上由真实 Intel macOS 与 Windows 文件系统生成。

## 下一步

1. 按 diagnostic 根因先改善 sequence outer/separator authority，再处理 cross 与局部异常；每次都先
   保住九张黄金的安全和 nominal 通过率。
2. Release 前补齐 Windows x64、Intel macOS 与 exFAT 实机证据；当前不创建 RC、tag 或 Release。
