# X5 Crop 用户手册

- 当前开发版本：**V4.9**
- 当前稳定发布：**v4.2.8**

X5 Crop 将 Hasselblad / Imacon X5 片夹扫描得到的长条 TIFF 自动拆分为单张 TIFF。
只有几何已经解决且输出保护可行的结果才会导出，其余文件进入复核。

日常使用请从 [GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases)
下载 `X5-Crop-vX.X.zip`，不要下载 GitHub 自动生成的 Source code 压缩包。

## 安装与启动

首次使用时运行对应安装器：

```text
macOS:   install/X5_Crop_Mac_install.command
Windows: install/X5_Crop_win_install.bat
```

安装器检查或安装 `numpy`、`tifffile`、`imagecodecs` 和 `Pillow`。macOS 安装器只处理
当前 Release 文件夹的启动权限和 quarantine，不建立系统级信任。

将入口、启动器和 TIFF 放在同一个文件夹：

```text
X5_Crop.py
X5_Crop_Mac.command 或 X5_Crop_win.bat
*.tif / *.tiff
```

启动方式：

```text
macOS:   双击 X5_Crop_Mac.command
Windows: 双击 X5_Crop_win.bat
```

macOS 无法双击时，在该文件夹的 Terminal 中运行：

```bash
/bin/bash X5_Crop_Mac.command
```

交互启动器依次询问：

```text
format:
partial mode? [y/n, return=no]:
count:
debug analysis? [y/n, return=no]:
```

只有 partial mode 会询问 `count`；Return 或 `auto` 表示自动判断。

## 格式与模式

| 输入 | 格式 | Full 张数 |
|---|---|---:|
| Return / `135` | 135 | 6 |
| `dual` / `135 dual` / `135-dual` | 135 双条 | 12 |
| `half` | 半格 | 12 |
| `xpan` | XPAN | 3 |
| `645` | 120-645 | 4 |
| `66` | 120-66 | 3 |
| `67` | 120-67 | 3 |

- 照片铺满片夹时使用 full。
- 片头、片尾、局部片条或未铺满片夹时使用 partial。
- XPAN 和 120-66 的完整三张片条如果未铺满画布，也使用 partial。
- `135-dual` 主要用于完整双条；证据不足时保持 REVIEW。

## 检测与安全边界

- 原始 TIFF 永不修改；输出写入新文件。
- 输出保留位深、通道结构、ICC/色彩空间、resolution metadata、其它 metadata 和已知
  无损压缩行为。
- TIFF DPI/PPI 只作为 I/O metadata 保存，不参与检测。已知单条片夹由像素长短比匹配
  物理画布并计算 px/mm；未知或竞争画布保持 REVIEW。
- 自动校斜不可关闭。Detection 在分帧前联合观测真实照片的共享边缘；deskew、mapped
  pair、共享短轴和照片尺寸消费同一证据，旋转后不重新测量短轴。
- 理论位置只缩小计算范围，不能产生 supported evidence。扫描外沿、单边缘、分数或执行
  预算都不能代替真实双边像素证据。
- 只有基础几何安全解决后才应用 bleed。Bleed 不能改变 geometry、Gate 或 output
  protection。

## Debug Analysis

Debug Analysis 是 dry run：执行完整检测并写出 JPG 与报告，但不导出正式裁切 TIFF。

```text
x5_crop_output/_debug_analysis/
```

每张 JPG 固定显示：

1. source 物理画布、照片共享边缘 fragment、witness 与不确定度；
2. mapped pair、共享短轴、`FrameSlot` 与 `FrameCropEnvelope`；
3. 长轴 boundary、separator 与最终框。

没有 selected pair 时仍显示 typed failure 和紧凑观测摘要。Report 与 Debug 只读取
detection evidence，不重算几何，也不作为 cache。

状态：

- `PASS`：自动导出。
- `REVIEW`：不自动导出。
- `RUNTIME ERROR`：detection 已完成，但后续运行阶段失败。

## 输出

```text
x5_crop_output/
  *_01.tif
  *_02.tif
  needs_review/
  _debug_analysis/
  x5_crop_report.jsonl
  x5_crop_summary.csv
  x5_crop_run_manifest.jsonl
```

- `needs_review/` 保存原始 TIFF 副本，供外部人工处理。
- `x5_crop_report.jsonl` 是 current-schema 机器审计记录。
- `x5_crop_run_manifest.jsonl` 记录每个输入的最终结果、实际输出和运行指标。
- 普通运行不会覆盖已有裁切；`--overwrite` 可显式覆盖。

默认 bleed 为长轴 20 px、短轴 10 px，只影响最终输出。

## 命令行

```bash
# 完整参数
python3 X5_Crop.py --help

# 交互模式
python3 X5_Crop.py --interactive

# full 自动裁切
python3 X5_Crop.py . --format 135 --strip full

# Debug Analysis dry run
python3 X5_Crop.py . --format 135 --strip full --report --debug-analysis --dry-run

# partial
python3 X5_Crop.py . --format 135 --strip partial --report

# 单进程
python3 X5_Crop.py . --format 135 --strip full --jobs 1
```

`--export-review` 只允许导出几何已经解决且输出保护可行的 REVIEW crop；它不能绕过
provisional geometry 或未解决的保护范围。

## 卸载与许可

删除 X5 Crop 文件夹即可移除程序和该文件夹中的输出。卸载器只清理用户级 Python 依赖，
不会删除 Python；这些依赖也可能被其它工具使用。

```text
macOS:   install/X5_Crop_Mac_uninstall.command
Windows: install/X5_Crop_win_uninstall.bat
```

许可证：MIT。完整文本见
[GitHub LICENSE](https://github.com/rrriiicccooo/X5-Crop/blob/main/LICENSE)。
