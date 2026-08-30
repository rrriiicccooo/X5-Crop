# X5 Crop V5 用户手册（开发预览）

- 范围：仓库 `main` 上尚未发布的 V5 源码
- 当前公开稳定版：v4.2.8；命令与行为不同，请使用该版本随包文档
- 适用输入：format 与曝光 slot 数已知的 Hasselblad / Imacon X5 片夹扫描

## 产品行为

X5 Crop 用已知 format 的设计尺寸先验建立该 source 的有界物理模板，而不是做通用照片边界识别。只有
当整张 source 的每个 slot 都能形成唯一、安全、可直接使用的裁切时，才写出正式 TIFF；否则整张进入
`needs_review`，不单独抢救部分 slot。

### Format 与 count

运行时必须提供 format。Count 可省略或明确指定：

- 省略 `--count`：确认使用匹配片夹的默认完整格数；
- `--count N`：确认实际有 N 个 slot；中间空曝光格也计数；
- count 必须为正数且不超过匹配片夹容量；
- `135-dual` 只有 12 格（每 lane 6 格）可自动处理，其它 count 进入 review。

默认完整格数：135=6、half=12、XPan=3、120-645=4、120-66=3；120-67 在普通片夹为 3、短片夹为 2；
135-dual 共 12。

程序不会从文件名、画面、片夹容量或空白格猜 format 与真实照片数，也不会删除、合并或重排空 slot。
V5 没有 full/partial mode。

### 自动批准与人工检查

V5 先从整条片带建立粗略支撑和共同方向，再把 format/count 编译成有界 W/H 模板，只在理论 outer、
separator 与 top/bottom 附近做有界局部测量。Format 尺寸是跨相机先验，不是要求每台相机严格相同的
片门常量；唯一 placement 中的直接边缘可分别闭合该 source 的共同 W/H，并保留原生位置。像素证据用于
对准模板和否决危险裁切，不能凭自身创造 format、count 或 placement。

缺失的单侧 start/end 只有在至少两张完整直接 Frame 已闭合 source W、且该 Frame 的另一侧直接可见时
才可推断；双侧都不可见的 Frame 不能由 Grid 凭空生成。Direct W/H 分别取证。Format 画幅比例可以在
经过黄金集校准、保留完整不确定性后让 W 约束 H：W/H compatibility 对所有 format 使用同一个“物理
毫米下限 + 相对比例”的计算方法，再由两轴 guard 推导各 format 的有界比例区间。它不能冒充直接
top/bottom、增加独立证据或用名义比例作零误差换算；比例校准不可用、与直接边界冲突或耗尽逐侧 5%
预算时，整张 source 保守进入 review。直接 top/bottom 始终优先保留原生位置。

同一已登记窗口会把多个高度的弱 gradient、tone 与 texture 信号联合检查。只有三个独立高度区域一致、
且唯一加强同一条直接边缘时，它才获得裁切坐标权限；未绑定或有多种解释的联合线只显示在 Debug 中，
不会生成新的 placement。

正常片带使用一个共享 pitch；每个直接且 ordinal 唯一的 separator 可以约束自己的宽/窄间隔，后续
Frame 只累加一次该处实测差值。多个已证明的间隔变化仍以一次有界传播处理；任一间隔存在多种解释、
缺少必要 authority、存在多个同样合法答案或未知必需 Frame 时保持 `needs_review`。
Contact 与 overlap 是 challenge，不是预定终态：标准 detector 与 Gate 能唯一证明安全时可以自动批准，
证据不足时安全 review 同样正确；V5 不为它们启用第二套 detector 或特殊 bleed。

选定 placement 后，程序才判断是否铺满片夹：只检查 outer 外侧能否再容纳一个 W，不回头搜索或居中。
135-dual 两条 lane 都必须满足完整性。

## 安全裁切、bleed 与 deskew

照片 aperture 的产品 bleed 为：

```text
start/end = max(0.15 mm, 0.7% W)
top/bottom = 0.25 mm
```

测量不确定性、局部 residual 与 bleed 共同消耗每侧最多 5% W/H 的安全外扩预算，边与边之间不能借用。
若直接观察到一对连续 outer support 完整包住固定 H，且总高度不超过 `1.1H`，它可以替代不可用的
aperture top/bottom；此时不再添加 0.25 mm cross bleed，但逐侧与联合对齐 padding 仍受 5% 预算保护。
任何真正需要的 source-space footprint 越界都进入 review，不会静默裁小。

二维内容只在最终 post-bleed polygon 上作保守否决：bleed 内的画面可以保留；可靠内容越过最终裁切边
会阻止自动输出。尘点、别名和极小角点接触不会单独移动边界或选择另一个 placement。

Deskew 是自动批准后的可选整理，不参与检测或 Gate。`--deskew auto` 仅在两侧共同支持稳定的小角度时
旋转；证据不足、冲突或超出清理范围时保持原始方向。`--deskew off` 完全跳过观测。旋转时，图像与已
确认安全的 polygon 使用同一 affine transform，再取轴对齐包络，因此角落可能出现少量黑色 no-data，
但不能切掉已保护内容。

## 安装开发源码

请取得完整仓库 checkout；不要只复制 `X5_Crop.py`，也不要把 GitHub 自动生成的 Source code 压缩包
当作稳定发布包。普通用户应下载 [GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases)
中的 v4.2.8。

V5 开发源码支持 Python 3.12–3.14：

- macOS：`tools/install/X5_Crop_Mac_install.command`
- Windows：`tools/install/X5_Crop_win_install.bat`

未来 V5 Release 包中的相同安装器位于 `install/`，不带 `tools/` 前缀。

安装器复用合适的全局 Python 和已有依赖，只补齐缺失项；未知 ownership 会在写入前停止。不会创建
私有 `.venv`，也不要求预装 Homebrew。

## 输入合同

V5 production 输入必须满足：

- 单页 TIFF；
- unsigned 16-bit；
- RGB 三通道、contiguous planar configuration；
- `NONE`、`LZW`、`DEFLATE` / `ADOBE_DEFLATE` 或 `ZSTD` 无损压缩；
- TIFF Orientation 1–8。

域外文件成为 `runtime_error`，不会静默转换。读取时规范化 Orientation，正式输出写
`Orientation=1`。

## 运行

图形启动：

- macOS：把 TIFF 放在 `X5_Crop_Mac.command` 旁并双击；
- Windows：把 TIFF 放在 `X5_Crop_win.bat` 旁并双击。

命令行示例：

```bash
python3 X5_Crop.py /path/to/scans --format 120-66 --count 2
```

主要选项：

- `input`：一个 TIFF 或目录，默认当前目录；
- `--output PATH`：全新输出目录；
- `--format`：`135`、`135-dual`、`half`、`xpan`、`120-645`、`120-66` 或 `120-67`；
- `-n, --count N`：显式 slot 数；省略表示确认默认完整 count；
- `--layout`：`auto`、`horizontal` 或 `vertical`；
- `--deskew`：`auto`（默认）或 `off`；
- `--jobs N`：source 并发，默认 1、上限 3；
- `--debug-analysis`：写 1,800 px 宽、高度自适应的三联诊断 JPG、开发报告和摘要，不写正式 TIFF；
- `--interactive`：交互确认 format、count、deskew 与 Debug Analysis。

没有 `--overwrite`。目标目录必须不存在；Debug Analysis 与正式裁切应使用不同的新目录，正式运行始终
重新读取原 TIFF。

## 状态、输出与退出码

每个输入只有一个终态：

- `approved_auto`：写出完整的一组正式 TIFF；
- `needs_review`：不写照片，保留最小缺失事实与建议操作；
- `runtime_error`：该输入失败，其它输入继续。

Debug Analysis 显示模板、实际观察、winner/runner、画幅比例原始/保护区间及推导 H、最终 footprint、
预算与首个阻断原因，并标明
`DESKEW APPLIED`、`ROTATION NOT NEEDED` 或 typed `DESKEW SKIPPED`。它只读取同次检测事实，不会
重新求解。

默认输出：

```text
x5_crop_output/
  原文件名_01.tif
  原文件名_02.tif
  needs_review/
  _debug_analysis/
  x5_crop_report.jsonl
  x5_crop_summary.csv
```

退出码：

- `0`：成功发布且没有 `runtime_error`；
- `1`：已发布但含 `runtime_error`，或全部输入失败；
- `2`：命令行、输入集合或运行前检查失败；
- `3`：全新输出目录无法安全发布。

正式 TIFF 只由 `tifffile + imagecodecs` 读写，并检查位深、通道、ICC、resolution、支持的 metadata、
无损压缩和 `Orientation=1`。程序先写 staging，全部完成后一次 rename；已有目标不会被遍历、覆盖或
删除。

License: MIT — [GitHub LICENSE](https://github.com/rrriiicccooo/X5-Crop/blob/main/LICENSE)
