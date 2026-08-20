# 项目记忆

更新：2026-08-20

这是唯一跨会话检查点。长期政策见 [AGENTS.md](../AGENTS.md)，运行合同见
[ARCHITECTURE.md](ARCHITECTURE.md)，版本变化见 [CHANGELOG.md](CHANGELOG.md)。现场 Git、源码、
原 TIFF、current report、Debug Analysis 和最新命令输出优先。

## 当前目标

V5 已收口为一条 current-only 模板对准主线：吸收 v4.2.8 从整条片带到理论位置附近精修的行为，
同时使用固定 W/H、独立证据、共享 deskew、最多一次 local advance、outer 权限分层、联合输出保护
和 typed Gate。下一阶段只按真实根因提高正常片条通过率；不得降低黄金通过率、产生黄金错误自动
批准，或用 111 张无真值样片反向调出特殊规则。V5 尚未发布。

## 已冻结事实

- 输入只有 format + 可选 count，没有 full/partial mode 或长轴居中。是否铺满在 selection 后仅以
  outer 外侧能否再容纳一个 W 判断；`135-dual` 只有 12=6+6 可自动处理。
- Coarse aggregate 只定位有限精测区域。已注册的短轴 trace 若直接形成 source-wide 双侧 track，
  可以独立提供共同方向；只有完整包含 H 且总 span 不超过 `1.1H` 的唯一 pair 才能成为 enclosing
  输出边界。
- Region/band 负责物理拓扑，edge 负责局部定位。Band center 可帮助 phase/pitch；band width 只属于
  material gap、局部拓扑和输出保护，不能否决全局 phase。
- Aperture bleed 为 sequence `max(0.15 mm, 0.7% W)`、cross `0.25 mm`，四边单边自动保护上限
  均为 5%。Enclosing top/bottom 不加 cross bleed，使用总 span `<=1.1H` 的独立合同。
- 安全层只消费唯一 placement 的联合可行状态，不合并 runner-up、不分别相加不能同时发生的最大
  误差、不重复计算固定 W，也不静默裁小越界 footprint。
- Deskew 同时属于检测与输出。轻微弯曲只作为共同直线 residual 进入安全范围；首版不拟合曲线。
- Contact 与 overlap 没有用户确认黄金；S098 不属于 overlap。当前只诊断 signed local delta 并
  review，不建第二套 detector 或特殊 bleed。
- Detector 使用原图生成的有界 8-bit gray；正式输出从原始 uint16 RGB 做 per-frame 反向 affine
  采样。Lane authority 外写黑色无数据像素，不能把插值上限误当背景值而写出全黑 TIFF。

## 当前证据边界

- Fresh `tools/verify full`：366 tests 通过，skip 2；compile、configuration、cohort、shell 与 version
  contract 通过。
- Fresh 九张黄金：七张正确 `approved_auto`；S055、S098 两张 challenge 安全 `needs_review`；
  9/9 安全，没有 nominal 通过率回退或错误自动批准。
- Fresh 111-source diagnostic：111/111 工程合同通过，40 张自动批准、71 张 review；recognition
  accuracy 仍为 `not_assessed`。Review 根因是 placement 唯一性 27、direct-use budget 13、
  output footprint 12、content veto 8、local advance 6 和无完整 placement 5。
- 正式 CLI 已重新写出 S027 的 6 张 uint16 RGB TIFF；六张均有非零像素和完整动态范围，验证了
  affine 输出不是全黑。冻结依赖已同步为 NumPy 2.5.2、tifffile 2026.8.16 和 imagecodecs
  2026.8.16。Clean current commit 的 24-source 完整路径已满足 mean `<=5 s/input`；profiling 显示
  最终 sampling 是首要热点，其次是启动/导入和模板对准，TIFF 解码与写出不是当前主瓶颈。精确
  机器绑定结果只保存在 ignored performance receipt 中。

## 开放风险与下一步

1. 111 张中最大的剩余缺口是 phase/placement 唯一性。先用 Debug、measurement replay 和必要的
   人工复核区分错误候选与真实多解，再改善 separator-center lattice、ordinal binding 或 outer
   anchor；不得用 coarse 距离、强度分数或 holder 长轴中心替 placement 选答案。
2. Output footprint 与 direct-use budget 失败必须继续区分真实 source 越界、联合几何过宽和测量
   residual；不能靠放宽 5% 或 1.1H 提高通过率。
3. Release 前在同一最终 commit 上重建 accuracy、performance 和目标平台 receipt，并补齐 Windows
   x64、Intel macOS 与 exFAT 实机证据；在此以前不创建 RC、tag、Release 或公开 ZIP。
