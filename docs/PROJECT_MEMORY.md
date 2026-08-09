# 项目记忆

更新：2026-08-09

这是唯一跨会话检查点。长期政策见 [AGENTS.md](../AGENTS.md)，当前系统见
[ARCHITECTURE.md](ARCHITECTURE.md)，版本变化见 [CHANGELOG.md](CHANGELOG.md)。Git、源码、
原 TIFF、current report、Debug Analysis 和现场命令输出始终优先。

## 当前目标

仓库已经是唯一 V5 current-only runtime。工具与文档审计已闭合；下一阶段单独人工诊断黄金
失败，顺序为 S109 → S062 → S051。只修改通用 evidence、geometry 或 safety owner；不增加
样片规则，不放宽逐边 direct-use budget，并在每次检测变化后重跑全部黄金、111-source
diagnostic 和两遍性能。

V5 在黄金准确率与最终平台证据闭合前不生成 RC、tag、GitHub Release 或公开 ZIP。公开稳定版
仍为 `v4.2.8`。

## 已验证检查点

- `d2efbcb7` 完成工具与文档审计并已同步 GitHub。生产默认 `--jobs 1`，显式 2/3 保留；
  Debug Analysis 使用 detected/selected TOP/BOTTOM、detected/selected START/END 与 final
  safety/output 三联自适应布局。
- 该 checkpoint 的 `tools/verify full` 为 166 tests 通过、3 项平台条件跳过；GitHub Verify 在
  四个 runner × Python 3.12–3.14 共 12 个 job 全部通过。
- 2026-08-09 现场运行十四项黄金：S027、S035、S091 explicit/auto 与 S094 通过；S055
  explicit/auto 和 S098 为可接受的安全 `needs_review`；失败仍固定为 S051、S062、S109 的
  explicit/auto 六项。
- 111-source cohort 的 111 个 source identity 当前完整。最近一次 111/111 工程运行不是本轮
  audit tree 的新证据，检测变化后必须重跑。
- 用户已确认 Windows x64 实机验证曾执行通过；平台 receipt 绑定 commit，不能替代最终 release
  commit 的 Apple Silicon、Windows x64 与 Intel macOS 证据。

## 验证边界与开放风险

- 阶段性的 non-detection freeze 已删除；它在后续合法 Debug 修改后失效并阻断 platform，不能
  继续充当当前验证 owner。Detection 回归直接使用 accuracy comparator、current-schema report
  comparison、111-source diagnostic 与性能证据。
- 当前工作区没有绑定最新 HEAD 的 production performance receipt；此前按用户决定跳过了一次
  `jobs=1` 提交的性能生成。下一次检测或 runtime 变化必须重新生成，不得复用旧 receipt。
- 六个 nominal 黄金失败仍是发布 blocker。本轮只确认集合，没有分析或试修。
- Intel macOS 实机 receipt 仍是明确外部待办。CI、源码相同或验证包存在都不能代替它。

## 精确下一步

1. 新开人工黄金诊断，依次处理 S109、S062、S051；每次只改一个通用物理 owner。
2. 检测完成后重跑十四项黄金、111-source diagnostic、24-source 两遍性能与全局残留审计。
3. 在最终 release commit 上重新生成 Apple Silicon、Windows x64 与 Intel macOS 实机 receipt，
   然后再决定是否制作 RC。
