# 项目记忆

更新：2026-08-18

这是唯一跨会话检查点。长期政策见 [AGENTS.md](../AGENTS.md)，运行合同见
[ARCHITECTURE.md](ARCHITECTURE.md)，版本变化见 [CHANGELOG.md](CHANGELOG.md)。现场 Git、源码、
原 TIFF、current report、Debug Analysis 和最新命令输出优先。

## 当前目标

从上次推送以来确认的主线已收口为一条 V5 current-only runtime：v4.2.8 的“先看
整条片带，再在理论位置附近精修”，与 V5 的固定模板、独立证据、共享 deskew、
最多一次 local advance、outer 权限分层、联合输出保护和 typed Gate 统一。当前工作是
在不改变 observation、placement、winner/runner 与 provenance 的前提下继续减少内存和
完整路径耗时，并按 diagnostic 根因改善正常片条 review。V5 尚未发布。

## 已冻结事实

- 输入是 format + 可选 count，没有 full/partial mode 或长轴居中权限。是否铺满只在 selection
  后用 outer 外侧能否再容纳一个 W 判断。`135-dual` 只有 12=6+6 可自动处理。
- Production 从 `CoarseStripSupport` 和共同方向出发，只在理论 outer、separator 与
  top/bottom 附近精修。Region/band 优先建立物理拓扑；edge 只做局部定位。
- `OuterBoundaryObservation` 不能直接宣告 `PhotoGroupOuter`。Aperture 使用固定 H
  闭环与正常 bleed；直接、连续且完整包住 H 的 enclosing support 可作为另一种输出边界，
  但不加 cross bleed，总高度不超过 `1.1H`。
- Aperture bleed 为 sequence `max(0.15 mm, 0.7% W)`、cross `0.25 mm`；四边单边
  自动保护上限均为 5%。安全层只消费唯一胜出 placement 的联合可行集，不合并落选位置、
  不分别相加不能同时发生的最大误差、不静默裁小越界 footprint。
- Deskew 同时属于检测与输出几何。轻微弯曲作为共同直线残差进入安全范围，首版不拟合
  曲线或逐帧方向。
- Contact 和 overlap 没有用户确认黄金；S098 不属于 overlap。当前只诊断 signed local
  delta 并 review，不建第二套 detector，不开启特殊 bleed。
- 正式 TIFF 域只有单页 uint16 RGB YXS。Detector 从原图分块生成 8-bit gray；输出在
  placement 确定后直接从原图做 per-frame 反向 affine ROI 采样，不旋转整张大图。

## 当前证据边界

- Fresh `tools/verify full` 通过：358 tests，skip 2；compile、configuration、cohort、shell 与
  version contract 通过。
- Fresh 九张黄金全部安全：七张正确 `approved_auto`，S055、S098 两张 challenge 安全
  `needs_review`；没有错误自动通过或 nominal 通过率回退。
- Fresh 111-source diagnostic 全部完成：32 张自动批准、79 张 review。主要根因是
  placement/phase/cross 唯一性 40、content veto 14、output footprint 或 direct-use precision 18、
  local advance 5 和无完整 placement 2。该队列的 recognition accuracy 仍为 `not_assessed`。
- 本轮两张黄金的完整 profile 显示，streaming gray 与通道缓冲复用将进程峰值 RSS 约降低
  21%–27%；当前真正热点仍是 affine sampling，其次是 startup/import 和部分 template
  alignment。3 秒是 challenge，正式 24-source 平均上限仍为 5 秒。正式数值只以绑定
  clean commit 的 ignored performance receipt 为准，不复制到 tracked 文档。

## 开放风险与下一步

1. 按 diagnostic 根因先改善正常 sequence outer/separator authority，再处理 cross 唯一性和局部
   异常；每次都保持黄金安全与 nominal 通过率。
2. 一个用户明确的 source-local phase anchor 可作为未来人工救援；它必须是记录在 provenance 中
   的 authority，复用同一 solver 和 Gate，不是 fallback 或全局样片规则。当前不进入 production。
3. Release 前仍需在最终 release commit 上重建 accuracy、performance 和目标平台 receipt，并补齐
   Windows x64、Intel macOS 与 exFAT 实机证据。当前不创建 RC、tag 或 Release。
