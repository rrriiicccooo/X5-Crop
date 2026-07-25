# X5 Crop 更新日志

本文件只记录版本级行为、验证边界与回滚背景。当前架构见 `ARCHITECTURE.md`，用户操作见
`docs/user-guide.zh-CN.md` 与 `docs/user-guide.en.md`。

- 当前开发版本：**V4.9**
- 当前稳定发布：**v4.2.8**

## V4.9 当前开发线

V4.9 是 current-only 的物理模型与源码重构。历史 PASS/REVIEW、report schema、人工标签
和裁切 geometry 不是兼容目标。

### 2026-07-26：黄金基线、文档与仓库收束

- 九张黄金样片均已由用户确认，形成绑定原图、标注副本、proposal snapshot 与复核 JPG
  hash 的本地 baseline。八张属于 `nominal_calibration`；非矩形、片距不稳的 `S098`
  作为 `irregular_geometry_stress` 保留，但不参与正常容差估计。Production detector
  阈值仍未据此调整。
- `S055` 的正确帧数为四。红线转换器会拒绝“声明帧数少于强短边证据”的输入，不能排序后
  静默丢弃人工笔迹。
- 人工 baseline 权限只来自绑定 source SHA 的用户直接标注与明确 JPG 确认，或独立校准的
  外部测量。模型视觉、OpenCV、SciPy、X5 Crop、生成 JPG 与算法一致只能产生非权威
  proposal。
- 校准目标采用“共享照片边缘 → deskew/共享短轴 → 成对长轴边缘 → 安全矩形 → 独立
  bleed”。验收使用黄金集校准的方向性容差，不追求数学 `0 px`；危险向外越界不得通过，
  bleed 不能掩盖错误基础几何。
- 删除 641 个与 Git history 重复的 tracked source snapshot；历史版本由 Git history 与
  release tags 恢复，current tree 不再维护 `archive/`。
- 测试审计未发现重复 test body、空 test module、未使用 public support owner 或无静态
  owner 的 active Python module，因此保留全部 current contracts。
- 文档改为中文内部真相源与独立中英文公共发布文档。根 `README.md` 只保留精简双语入口；
  发布包改为 `README_中文.txt`、`README_English.txt`、`快速启动.txt` 与
  `Quick_Start.txt`，不再包含逐段中英混排文档或旧文件名。
- `LICENSE` 保留在 GitHub，本地 sparse checkout 不保存。

### 当前累计行为

- `FramePhysicalSpec` 只保存照片尺寸；`ScanCanvasPhysicalSpec` 只保存片夹扫描画布。
  TIFF DPI/PPI 仅作 I/O metadata。
- 已知单条画布由 source pixel aspect 唯一匹配并生成 `CanvasPixelScale`；无匹配或竞争
  profile 保持 typed unresolved。`135-dual` 不虚构固定画布。
- 分帧前从任意清晰区域形成与材料和极性无关的 photo-edge observation。连续 ridge
  成为不可拆 fragment；法向联合区域同时约束 top、bottom、照片高度、中心、
  containment 与完整 `FrameSizeMm`。
- `PhotoEdgePairEvidence` 是唯一边缘身份真相。Deskew、mapped pair、
  `SharedShortAxisPlan` 与 frame sequence 只消费同一 selected pair；旋转后不重新测量
  短轴。
- Pair identity、transform precision 与全 workspace shared-axis safety 独立判断。
  `CandidateGate` 判断候选，`DecisionGate` 独占最终 PASS/REVIEW。
- 当前 report revision 为 `cross_region_photo_edge_geometry`。Report 与 Debug 只读
  typed evidence，不保存 dense response、不重算 geometry，也不作为 detection cache。
- `tools/` 的 current owner 只有 `verify`、`git/`、`release/`、
  `regression/compare.py` 与 `tests/`；退役 manual-reference regression chain 不再存在。

## 验证边界

- `tools/verify` 是唯一机械验证入口；Hook 与 CI 只调用它。
- Unit/contract、compile、configuration 与 release-package 检查只能证明结构一致性，
  不能证明真实照片边缘已经达到 production accuracy。
- 本地已有九条 user-confirmed crop baseline，但 production detector 尚未通过它们完成
  方向性误差量化或阈值校准。

## v4.2.8 稳定发布

v4.2.8 仍是面向普通用户的稳定 GitHub Release；V4.9 尚未替代它。

## 发布与回滚

- 发布包内容由 `tools/release/manifest.py` 独占，通过
  `python3 -m tools.release.build --version <version>` 构建。
- V4.9 是破坏性 current-only 迁移。回滚必须整体恢复物理模型、configuration、
  workspace、report schema、contracts 与 docs；不得混用旧人工 baseline、旧 deskew
  或旧 schema。
- 历史源码从 Git history 与 release tags 恢复，不在 current tree 复制 `archive/`。
