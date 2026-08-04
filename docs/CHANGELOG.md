# X5 Crop 更新日志

本文件只记录版本级行为、验证边界与必要回滚背景。当前源码结构见
[ARCHITECTURE.md](ARCHITECTURE.md)。

## V4.9（开发中，尚未发布）

V4.9 是破坏性的 current-only 重构，不承诺旧 schema、reason、geometry、confidence 或
Debug parity。

### 固定格式 template-first 检测

- 用户提供的 format 与 count 仍是 authority；partial auto 使用匹配片夹容量，不猜真实
  照片张数。
- 检测从一次基础一维 profile 建立少量完整格式模板，再让整组像素证据确认 phase、pitch、
  local delta 与共同 direction。局部边线不再自行拼接 placement。
- Start/end 使用无独立 slope 的 `SideTransitionRegion`，最终严格正交于共同 top/bottom
  direction。增加无关局部线不能拖动已成立的 source direction。
- 同一 source 中所有正常照片共享真实宽高和两个 axis scales；设计尺寸 separation tolerance
  统一为 width 1.25%、height 0.40%。端部遮挡只限制可见位置，不改变真实尺寸。
- 理论节距由联合 source geometry 与 nominal gap 计算；确认的局部卷片异常只造成一次 phase
  step，不在后续每格重复扩散。
- 完整 groups 通过空间分离或 opposite-edge pair取得相位 authority。孤立线只有在唯一整组
  证据成立时才能排除；同等强度竞争全部进入安全 union。
- 删除旧 direction candidate 排名、phase splice、通用 DP、short-candidate 笛卡尔积、blank
  geometry、content-region ownership 与相关兼容层。

### 安全输出

- `SafeCropEnvelope` 是 footprint 与 mapped box 的唯一 owner。Retained full footprints 与
  canonical minimum guard只取 outer union，再应用一次 1 source-pixel interpolation guard。
- 连续 footprint vertices直接 transform；不再经过 source AABB 再映射，避免 deskew 二次
  膨胀。
- `start/end` 每边 direct-use budget 固定为设计宽度 5%，`top/bottom` 每边为设计高度 3%。
  Exact limit通过，任意正超量失败。
- 54/56 等 sampling-equivalent 输出仍保留各自 physical legal-window constraint；批准要求
  输出落在全部 retained interpretations 的合法窗口交集中。
- Authority 不得裁掉 retained placement 或 canonical；只允许裁掉 guard 并记录 saturation。
- Writer 对每个 approved ROI 只从原 TIFF 做一次 inverse-affine sampling；lane 外插值 taps
  使用背景，不采入另一 lane。

### 决策、报告与工具

- 保留两个 Gate：CandidateGate 冻结 typed facts，DecisionGate 独占 final status 与 reasons。
  删除 unresolved 字符串解析、重复 check 列表和旧 competition vocabulary。
- Current report revision 为 `source_coordinate_format_placement_v2`；Debug Analysis 只读取
  current facts，不复制 detection 或 budget 算法。
- S062 current profile 为 `x5crop_fixed_sample_profile_v5`，只记录实际 template work；旧
  DP 字段不以零值墓碑保留。
- Performance comparator 只对 exact-hash 冻结基线提供专用 reader。Runtime、report、tests
  与 Debug 不保留旧 schema compatibility。
- Release builder继续从 modular `x5crop/` 自动生成 standalone `X5_Crop.py`，ZIP 内容只由
  `tools/release/manifest.py` 决定。

### 当前验证边界

- 本阶段先闭合 current architecture、synthetic contracts、111-source 工程合同、TIFF、
  Debug、standalone 与固定性能；不读取黄金 accuracy geometry。
- 因此阶段终点只能声明“架构 current、物理合同自洽、工作有界、性能合格”，不能声明真实
  照片识别准确率或 release-ready。
- 后续黄金阶段将从当前干净架构重新建立 current-only comparator，并验证真实 detection、
  containment、5%/3%、自动批准率与 deskew。不得恢复旧 runner 或兼容 reader。

## v4.2.8（当前稳定发布）

v4.2.8 仍是 GitHub Releases 中的稳定版本。它以快速一维 profile、理论节距附近搜索、basic
优先和按需 enhanced 获得良好速度与大多数场景的准确裁切；但使用 confidence、固定 bleed、
format-specific thresholds 与 best-score selection，不能作为 V4.9 的安全 authority。

V4.9 借鉴其高效测量顺序和小工作集，不恢复上述旧批准语义。

## 回滚与发布

- V4.9 若需回滚，必须整体恢复同一 Git commit 的 detector、configuration、schema、tests 与
  docs；不得混用版本组件。
- 发布包使用：

  ```bash
  python3 -m tools.release.build --version <version>
  ```

- 当前工作不创建 tag、GitHub Release 或公开 ZIP；只有后续 release-ready 验证完成后才能
  单独决定发布。
