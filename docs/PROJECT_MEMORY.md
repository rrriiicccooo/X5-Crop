# 项目记忆

更新：2026-08-26；行为源码检查点 `7eb69c29`，本次只同步文档。

本文件只保存跨会话继续工作所需的当前检查点。长期合同见
[ARCHITECTURE.md](ARCHITECTURE.md)，人工标注规则见
[MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md)，验证与协作规则见
[../AGENTS.md](../AGENTS.md)。

## 当前目标

继续使用本地标注器审核 `gold_calibration_v2`，以较低人工成本扩充经过用户确认的黄金样片。
机器 proposal 只负责起点；只有用户在原图坐标中明确确认、并重新核对 source SHA、format 与
显式 count 的任务，才有资格进入阻断型黄金 cohort。任何 v2 标注都不得自动晋升为黄金基线。

## 当前黄金验收语义

- 人工 polygon 不是百分之百真实内容边界，也不是 detector 的唯一正确答案；它表示用户确认的
  “最内侧可接受无 bleed 裁切”。
- 候选基础裁切与最终 post-bleed `required_source_footprint` 都不得切入 polygon 内侧；边、角及
  亚像素级向内越界均失败。数值 epsilon 只用于浮点比较，不能形成产品容差。
- 每一侧向外扩张的黄金验收上限为对应人工确认宽或高的 5%，另加具名的 0.5 px sampling-coordinate
  allowance；uncertainty、residual 与 bleed 共同消耗这项预算。
- 该合同适用于 gold v1、v2 及将来版本，也适用于所有 `boundary_use`。运行时 1.1H enclosing
  规则仍负责 placement 决策，黄金验收另行检查逐侧安全范围。

## 已验证检查点

- 仓库只有 V5 current-only production path；公开稳定版仍为 `v4.2.8`，V5 尚未发布。
- 黄金比较器已移除旧的 corner inward exception，并使用
  `x5crop_directional_minimum_acceptable_crop_v1` 合同及对应 baseline schema。
- S098 曾暴露约 0.290390 px 的真实向内越界。根因修复把直接约束 sequence start/end 的拟合线证据
  传入输出安全层，但不旋转 frame、不创建 phase authority，也不重复累计已有位置区间。修复后该边
  向外约 1.288997 px，样片仍为 `nominal`、`approved_auto`。
- `tools/verify accuracy`：现有 9 项黄金任务全部安全并自动批准。
- 正常 pre-push hook：427 项测试通过，跳过 2 项；compileall、cohort count、shell syntax、diff
  hygiene 与 version smoke 均通过。
- 当前 tracked cohort 为 9 项 `gold_accuracy_blocking` 与 110 项 `diagnostic_unreviewed`。后者只证明
  工程、authority、schema 与运行终止性，不提供 accuracy verdict。

## 验证边界与开放风险

- 检查点 `7eb69c29` 尚未重新运行 diagnostic、performance 或三平台验证。旧 diagnostic 分布和旧
  performance/platform receipt 不能证明当前 commit；性能 receipt 必须重新绑定最终 release commit。
- 机器 proposal、OpenCV/SciPy 拟合、生成 review JPG 与模型视觉都不具有 reference authority；
  不确定或无法由用户确认的边界保持 unresolved。
- 扩充 v2 只有在逐任务完成用户确认与独立 cohort 审计后，才能改变黄金 cohort；不能用当前 detector
  输出、通过率或样片特例反向制造黄金答案。
- 发布仍缺最终 commit 上的 accuracy、performance、依赖、TIFF、中文路径、文件系统恢复及 Apple
  Silicon macOS、Intel macOS、Windows x64 实机 receipt。

## 精确下一步

1. 逐张继续 v2 标注；在原生像素检查中审核机器线，按显式 count 确认每个 task，避免一次载入多张
   原 TIFF。
2. 用户确认后，逐项核对 source SHA、format、count、baseline schema 与 digest，再决定是否独立加入
   `gold_accuracy_blocking` cohort。
3. cohort 改动后运行 accuracy；detector 改动后补做 source-bound diagnostic，并只通过正常 hook 完成
   已覆盖的提交与推送验证，不手工重复同一套测试。
4. 仅在准备发布且 release commit 冻结后，重建 performance 与三平台 receipt。
