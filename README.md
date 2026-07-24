# X5 Crop

X5 Crop 将 Hasselblad / Imacon X5 片夹扫描得到的长条 TIFF 自动拆分为单张 TIFF。
它只导出几何与输出保护均已解决的结果，其余文件进入复核。

X5 Crop splits long TIFF scans from Hasselblad / Imacon X5 holders into
individual TIFF frames. It exports only when geometry is resolved and output
protection is feasible; every other result remains in review.

- 当前开发版本 / Active development: **V4.9**
- 当前稳定发布 / Stable release: **v4.2.8**

> 日常使用请下载 GitHub Releases 中的 `X5-Crop-vX.X.zip`，不要下载 GitHub 自动生成的
> Source code 压缩包。 / For normal use, download `X5-Crop-vX.X.zip` from
> GitHub Releases, not GitHub's generated Source code archive.

## 安装与启动 / Install And Run

首次使用时运行对应安装器：

Run the platform installer once:

```text
macOS:   install/X5_Crop_Mac_install.command
Windows: install/X5_Crop_win_install.bat
```

安装器检查或安装 `numpy`、`tifffile`、`imagecodecs` 和 `Pillow`。macOS 安装器只处理
当前 Release 文件夹的启动权限和 quarantine，不建立系统级信任。

The installer checks `numpy`, `tifffile`, `imagecodecs`, and `Pillow`. On macOS
it prepares only the current Release folder.

将入口、启动器和 TIFF 放在同一个文件夹：

Keep the entry script, launcher, and TIFF scans together:

```text
X5_Crop.py
X5_Crop_Mac.command 或 / or X5_Crop_win.bat
*.tif / *.tiff
```

启动方式 / Launch:

```text
macOS:   双击 / double-click X5_Crop_Mac.command
Windows: 双击 / double-click X5_Crop_win.bat
```

macOS 无法双击时，在该文件夹的 Terminal 中运行：

If macOS blocks double-click launch, run this in the same folder:

```bash
/bin/bash X5_Crop_Mac.command
```

交互启动器依次询问：

The interactive launcher asks:

```text
format:
partial mode? [y/n, return=no]:
count:
debug analysis? [y/n, return=no]:
```

只有 partial mode 会询问 `count`；Return 或 `auto` 表示自动判断。

`count` is asked only in partial mode; Return or `auto` enables automatic count.

## 格式与模式 / Formats And Modes

| 输入 / Input | 格式 / Format | Full 张数 / Count |
|---|---|---:|
| Return / `135` | 135 | 6 |
| `dual` / `135 dual` / `135-dual` | dual-lane 135 | 12 |
| `half` | half-frame | 12 |
| `xpan` | XPAN | 3 |
| `645` | 120-645 | 4 |
| `66` | 120-66 | 3 |
| `67` | 120-67 | 3 |

- 照片铺满片夹时使用 full。 / Use full when film fills the holder.
- 片头、片尾、局部片条或未铺满片夹时使用 partial。 / Use partial for heads,
  tails, short strips, or scans that do not fill the holder.
- XPAN 和 120-66 的完整三张片条如果未铺满画布，也使用 partial。 / A complete
  three-frame XPAN or 120-66 scan that does not fill its canvas also uses partial.
- `135-dual` 主要用于完整双条；证据不足时保持 REVIEW。 / `135-dual` is intended
  for complete dual strips and remains in REVIEW when its lane evidence is incomplete.

## 检测与安全边界 / Detection And Safety

- 原始 TIFF 永不修改；输出写入新文件。 / Source TIFFs are never modified.
- 输出保留位深、通道结构、ICC / 色彩空间、resolution metadata、其它 metadata
  及已知无损压缩行为。 / Output preserves bit depth, channels, ICC/color space,
  resolution metadata, other metadata, and known lossless compression behavior.
- TIFF DPI/PPI 只作为 I/O metadata 保存，不参与检测。已知单条片夹由像素长短比匹配
  物理画布并计算 px/mm；未知或竞争画布保持 REVIEW。 / TIFF DPI/PPI is metadata
  only. A known single-strip canvas is matched from pixel aspect and supplies px/mm;
  unknown or competing canvases remain in REVIEW.
- 自动校斜不可关闭。Detection 在分帧前从任意清晰区域联合观测真实照片上下边缘；
  deskew、mapped pair、共享短轴和照片尺寸只消费同一边缘证据，旋转后不重新测量短轴。
  / Automatic deskew is mandatory. Before frame solving, detection joins clear local
  regions into the real top/bottom photo edges; deskew, mapped geometry, shared-axis
  safety, and frame size consume that same evidence without post-rotation remeasurement.
- 理论位置只缩小计算范围，不能产生 supported evidence。扫描外沿、单边缘、分数或执行
  预算都不能代替真实双边像素证据。 / Theory only bounds computation. Scan extrema,
  a single edge, scores, or work budgets cannot replace observed paired pixels.
- `CandidateGate` 判断候选物理证明，`DecisionGate` 独占最终 PASS/REVIEW。
  / `CandidateGate` assesses candidate proof; `DecisionGate` alone creates PASS/REVIEW.

内部运行流、坐标、不确定度与源码分层见 [ARCHITECTURE.md](ARCHITECTURE.md)。

See [ARCHITECTURE.md](ARCHITECTURE.md) for runtime flow, coordinates, uncertainty,
and source ownership.

## Debug Analysis

Debug Analysis 是 dry run：执行完整检测并写出 JPG 与报告，但不导出正式裁切 TIFF。

Debug Analysis is a dry run: it runs complete detection and writes JPG/report
artifacts without exporting final crop TIFFs.

```text
x5_crop_output/_debug_analysis/
```

每张 JPG 固定显示三类证据：

Each JPG shows three evidence groups:

1. source 物理画布、照片上下边缘 fragment、witness 与不确定度；
2. mapped pair、共享短轴、`FrameSlot` 与 `FrameCropEnvelope`；
3. 长轴 boundary、separator 与最终框。

1. source canvas and top/bottom photo-edge fragments, witnesses, and uncertainty;
2. mapped pair, shared short axis, `FrameSlot`, and `FrameCropEnvelope`;
3. long-axis boundaries, separators, and final boxes.

没有 selected pair 时仍显示 typed failure 和紧凑观测摘要，不绘制密集 response 或重复
observation。Report 与 Debug 只读 detection evidence，不重算几何，也不作为 cache。

Without a selected pair, typed failures and compact summaries remain visible.
Reports and Debug read detection evidence; they neither recompute geometry nor act
as a cache.

状态 / Status:

- `PASS`: 自动导出。 / Auto-exported.
- `REVIEW`: 不自动导出。 / Not auto-exported.
- `RUNTIME ERROR`: detection 已完成，但后续运行阶段失败。 / Detection completed,
  but a later runtime stage failed.

## 输出 / Output

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

- `needs_review/` 保存原始 TIFF 副本，供外部人工处理。 / `needs_review/` contains
  source-TIFF copies for external handling.
- `x5_crop_report.jsonl` 是 current-schema 机器审计记录。 / The report is the
  current-schema machine audit record.
- `x5_crop_run_manifest.jsonl` 记录每个输入的最终结果、实际输出和运行指标。
  / The run manifest records terminal outcome, actual outputs, and runtime metrics.
- 普通运行不会覆盖已有裁切；`--overwrite` 可显式覆盖。 / Normal runs do not
  overwrite existing crops; `--overwrite` opts in.

默认 bleed 为长轴 20 px、短轴 10 px。Bleed 只影响最终输出；它不能改变 candidate
geometry、Gate 或 output protection。

Default bleed is 20 px on the long axis and 10 px on the short axis. Bleed affects
final output only; it cannot change candidate geometry, gates, or output protection.

## 命令行 / Command Line

```bash
# 完整参数 / full help
python3 X5_Crop.py --help

# 交互模式 / interactive
python3 X5_Crop.py --interactive

# full 自动裁切 / normal full crop
python3 X5_Crop.py . --format 135 --strip full

# Debug Analysis dry run
python3 X5_Crop.py . --format 135 --strip full --report --debug-analysis --dry-run

# partial
python3 X5_Crop.py . --format 135 --strip partial --report

# 单进程 / disable parallel workers
python3 X5_Crop.py . --format 135 --strip full --jobs 1
```

`--export-review` 只允许导出几何已解决且 output protection 可行的 REVIEW crop；它不能
绕过 provisional geometry 或未解决的保护范围。

`--export-review` exports a REVIEW crop only when geometry is resolved and
output protection is feasible. It cannot bypass provisional geometry or unresolved
safety.

## 卸载与许可 / Uninstall And License

删除 X5 Crop 文件夹即可移除程序和该文件夹中的输出。卸载器只清理用户级 Python 依赖，
不会删除 Python；这些依赖也可能被其它工具使用。

Delete the X5 Crop folder to remove the program and its local outputs. Uninstallers
remove user-level dependencies, not Python itself; those dependencies may be shared.

```text
macOS:   install/X5_Crop_Mac_uninstall.command
Windows: install/X5_Crop_win_uninstall.bat
```

License: MIT，见 / see [LICENSE](LICENSE).
