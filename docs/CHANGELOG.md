# X5 Crop 更新日志

本文件只记录版本级行为与验证边界。V5 合同、运行流、数值定义和源码 owner 见
[ARCHITECTURE.md](ARCHITECTURE.md)；当前目标、证据、风险与下一步见
[PROJECT_MEMORY.md](PROJECT_MEMORY.md)。逐次实现与实验留在 Git history，不在此重复。

## V5（开发中，尚未发布）

### 行为边界

- V5 只有一条 current-only production path。输入 format 必须由用户提供，count 可确认默认值或明确指定；
  空曝光格保留，任何必需 slot 不安全都会使整张 source 进入 `needs_review`。
- 每条 source 使用共同 W/H 和固定 `1.1W × 1.1H` 原图坐标窗口，四边 5% 留边包含基础保护；程序只选择
  位置。可见内容、物理边界、typed evidence、source/lane 安全与人工 reference 继续按架构合同核验。
- 只有真实 TIFF 外缘允许 source clipping；内部 authority 边界不能用缩小窗口绕过。Deskew 只在批准后
  整理，不参与检测或 Gate。Debug Analysis 复用同次检测事实，不取得裁切或自动输出权限。
- 正式 TIFF 只在整张 source 通过安全准入后发布；输出先写 staging，再原子发布到全新目录，保留既有目标。

### 验证边界

- `tools/verify` 是工程、准确性、性能、平台和 Hook 的统一入口；开发 gold、诊断报告、CI 通过或安全
  Review 都不能替代架构第 14 节定义的 release gate。
- 发布资格必须把 accuracy、TIFF/metadata、性能、安装、目标平台、打包和 Hook/CI 证据绑定同一最终
  release commit。V5 当前仍为开发预览，未创建 RC、tag、GitHub Release 或公开 ZIP。

## v4.2.8

公开稳定版及其随包文档见 [GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases)。V4 命令与 V5
开发预览不同，不能用本文件替代对应版本文档。
