# X5 Crop 用户手册

- 当前公开稳定版本：v4.2.8
- 仓库当前源码：V5 current-only，尚未公开发布
- 输入定位：用户已经知道 format、片条模式及必要 count 的 Hasselblad / Imacon X5 片夹扫描

## 产品行为

X5 Crop 的目标是自动产生足够安全且不切掉真实照片内容的 TIFF。用户提供胶片格式；程序使用
扫描像素、固定物理尺寸、片夹画布、张数与顺序共同判断。只有内容保护、多余边缘限制、变换和
TIFF 写出均成立时才输出正式照片，否则整张 source 进入 `needs_review`，不做部分 slot 挽救。

程序不承诺恢复唯一的真实照片边界，也不从文件名猜 format 或 count。`partial --count auto`
使用匹配片夹对该格式的有效最大容量；没有 blank suppression，因此空白 slot 也可能输出。
相邻照片接触或局部重叠时，相邻输出可以重复包含少量 source pixels，以保护真实内容。

## 安装

从 [GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases) 下载
`X5-Crop-vX.X.zip`。不要使用 GitHub 自动生成的 Source code 压缩包。

发布包支持 Python 3.12–3.14，并固定以下依赖：

```text
numpy==2.5.1
scipy==1.18.0
opencv-python-headless==5.0.0.93
tifffile==2026.7.31
imagecodecs==2026.6.26
Pillow==12.3.0
```

运行平台安装器：

- macOS：`install/X5_Crop_Mac_install.command`
- Windows：`install/X5_Crop_win_install.bat`

安装器把依赖安装到目标 Python 的用户级 site，不建立私有 `.venv`。如果任一冻结依赖已经以
其它版本存在，安装器会在改动 package 前停止，不会静默升级、降级或覆盖。

## 输入合同

V5 正式输入域为：

- 单页 TIFF；
- unsigned 16-bit；
- RGB、三通道、contiguous planar configuration；
- `NONE`、`LZW`、`DEFLATE` / `ADOBE_DEFLATE` 或 `ZSTD` 无损压缩；
- TIFF Orientation 1–8。

不满足冻结域的文件会记录为 `runtime_error`，不会静默转换或猜测。Orientation 在读取边界转换
为正确视觉方向；检测、排序与裁切都在该方向工作，输出像素写为 `Orientation=1`。

## 运行

图形化启动：

- macOS：将 TIFF 放到启动器目录，双击 `X5_Crop_Mac.command`。
- Windows：将 TIFF 放到启动器目录，双击 `X5_Crop_win.bat`。

命令行示例：

```bash
python3 X5_Crop.py /path/to/scans \
  --format 120-66 \
  --strip partial \
  --count auto \
  --jobs 2
```

正式参数：

- `input`：一个 TIFF 或包含 TIFF 的目录；省略时为当前目录。
- `--output PATH`：输出目录；默认是输入旁的 `x5_crop_output`。
- `--format`：`135`、`135-dual`、`half`、`xpan`、`120-645`、`120-66`、`120-67`。
- `--layout`：`auto`、`horizontal` 或 `vertical`。
- `--strip`：`full` 或 `partial`。
- `--count N|auto`：partial 的明确张数或片夹容量；full 使用格式固定张数。
- `--jobs N`：source 并发数；默认 2，上限 3。数值库内部线程固定为 1。
- `--debug-analysis`：显式生成四层诊断 JPG；默认关闭。
- `--allow-best-effort-output`：明确接受未验证文件系统的较弱发布语义。
- `--interactive`：交互选择格式、模式、张数和 Debug Analysis。

没有 `--overwrite`。一次成功运行总是以完整新结果替换上一套可确认归属的 V5 输出。

## 状态与退出码

每个输入只有一个终态：

- `approved_auto`：写出完整正式照片 TIFF。
- `needs_review`：不写正式照片，将原扫描件复制到 `needs_review/`。
- `runtime_error`：该输入失败，不写它的照片；其它输入继续处理。

退出码：

- `0`：成功发布，且没有 `runtime_error`。
- `1`：成功发布但含 `runtime_error`，或全部输入失败且未发布。
- `2`：命令行、输入集合或运行前检查失败。
- `3`：输出事务状态歧义、发布或恢复失败。

如果全部输入均为 `runtime_error`，程序不发布空结果，上一套输出保持不动。

## 输出与安全替换

默认结构：

```text
x5_crop_output/
  原文件名_01.tif
  原文件名_02.tif
  needs_review/
  _debug_analysis/
  x5_crop_report.jsonl
  x5_crop_summary.csv
  x5_crop_run_manifest.jsonl
```

照片直接位于根部，不建立 `run-*` 或 source 子目录。`needs_review/` 和 `_debug_analysis/` 仅在
有内容时出现。

新运行先在输出目录旁建立完整内部事务目录。全部输入处理结束、正式 TIFF 复读通过、报告和
manifest 完整后，程序用两次同父目录 rename 发布新结果，再删除旧结果。程序异常或强制结束
后会在状态明确时恢复；突然断电造成状态歧义时保留 target、new、old 和 journal，要求人工
确认，绝不自动删除。

只有固定 owner marker、current manifest 和完整 inventory 全部匹配的旧目录才能自动替换。
额外文件、缺失文件、链接、junction、reparse point、旧 schema 或人工目录都会使程序停止。

## 文件系统与磁盘空间

已验证本地文件系统可直接运行。SMB、NAS、云盘同步目录、未验证 exFAT 或无法确认语义的文件
系统属于 best effort：

- 交互运行显示风险和目标路径，默认拒绝；
- 非交互 CLI 必须明确加入 `--allow-best-effort-output`。

该选择不能绕过锁、同文件系统、rename、路径安全或磁盘空间硬失败。运行前会为完整新结果、
报告、可选 Debug Analysis、事务开销和 32 MiB guard 做 invocation-wide 预算；旧结果在发布
成功前继续占用空间。

## TIFF 保真与隐私

正式 TIFF 仅由 `tifffile + imagecodecs` 读写。每张输出关闭写句柄后都会重新打开，并检查
16-bit RGB、三通道、contiguous planar、形状、像素、ICC、resolution、resolution unit、受支持
metadata、无损压缩与 `Orientation=1`。

普通运行不读取原 TIFF 来计算内容 SHA，不检查 Git、黄金样片或性能 receipt，也不启用
profiler 或故障注入。它只记录 `run_id`、输入序号、便携文件名、size、mtime、依赖/线程和输出
事务所需的轻量身份。Pillow 只在用户明确启用 Debug Analysis 后延迟导入。

## 当前验证边界

V5 已是仓库唯一运行时，并已建立合成 contracts、严格 TIFF/Orientation、正式 schema、
standalone 构建和可恢复平面输出事务。V5 仍未完成全部真实黄金准确率、24-source 性能和
Windows x64、Apple Silicon、Intel macOS 三个平台的正式 receipt，因此不能据此宣布 V5 已
release-ready 或所有平台已经正式支持。当前用户应继续使用公开稳定版 v4.2.8。

## 移除与许可

卸载依赖：

- macOS：`install/X5_Crop_Mac_uninstall.command`
- Windows：`install/X5_Crop_win_uninstall.bat`

卸载器只删除由 X5 Crop 引入、版本未变化且不再被其它 package 需要的依赖。

License: MIT — [LICENSE](../LICENSE)
