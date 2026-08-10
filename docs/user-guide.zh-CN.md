# X5 Crop 用户手册

- 当前公开稳定版本：v4.2.8
- 仓库当前源码：V5 current-only，尚未公开发布
- 输入定位：用户已经知道 format、片条模式及必要 count 的 Hasselblad / Imacon X5 片夹扫描

## 产品行为

X5 Crop 的目标是自动产生足够安全且不切掉真实照片内容的 TIFF。用户提供胶片格式；程序使用
扫描像素、固定物理尺寸、片夹画布、张数与顺序共同判断。只有内容保护、多余边缘限制、变换和
TIFF 写出均成立时才输出正式照片，否则整张 source 进入 `needs_review`，不做部分 slot 挽救。

程序不承诺恢复唯一的真实照片边界，也不从文件名猜 format 或 count。Full 使用格式固定张数；
partial 必须由用户输入这段片条实际包含的曝光格数，包括中间需要保留的空白曝光格。片夹容量只
校验上限，不能代替 count。交互启动时，缺失、无效或超过容量的 count 会要求重新输入；命令行
则以输入错误停止。程序不删除空白 slot。

Format 决定照片矩形的物理尺寸。检测只负责根据片条方向、照片上下边缘、照片间黑带、共同尺寸
和局部卷片关系放置这些矩形，再把边缘测量所需的最小安全范围纳入输出。最终每一边都必须通过
以 format 尺寸为基准的 5%（start/end）或 3%（top/bottom）限制。相邻照片接触或重叠时，
相邻输出可以重复包含同一段 source pixels；这不是额外边缘，也不会改变照片数。

## 安装

从 [GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases) 下载
`X5-Crop-vX.X.zip`。不要使用 GitHub 自动生成的 Source code 压缩包。

发布包支持 Python 3.12–3.14，并固定以下可导入模块版本：

```text
numpy       2.5.1
scipy       1.18.0
cv2         5.0.0
tifffile    2026.7.31
imagecodecs 2026.6.26
PIL         12.3.0
```

运行平台安装器：

- macOS：`install/X5_Crop_Mac_install.command`
- Windows：`install/X5_Crop_win_install.bat`

安装器先选择一份受支持的全局 Python，再逐项检查实际可导入模块、版本和来源。版本已经满足时
直接复用，不因模块来自 Homebrew、pip 或其它来源而重复安装。缺失模块才使用该 Python 的用户级
pip 安装最小的冻结 binary wheel；已有版本不符时，能够确认 Homebrew 或 pip ownership 才沿用
原 package manager 更新。来源无法安全确认时会在改动前停止，不用第二份包遮盖未知环境。

Homebrew 不是前置条件，安装器不会为了 OpenCV 强制安装 Homebrew。缺少 `cv2` 时，默认用户级
fallback 是 `opencv-python-headless==5.0.0.93`；已经可用的 Homebrew `opencv`、pip OpenCV 或
其它 provider 都保持原样。用户级 site 不建立私有 `.venv`，因此同一 Python 可在任意文件夹
运行独立的 `X5_Crop.py`。卸载器只删除收据确认由 X5 Crop 新增且未被其它包使用的用户级包，
不会回滚已有包或 Homebrew 更新。

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
  --count 2
```

命令行参数：

- `input`：一个 TIFF 或包含 TIFF 的目录；省略时为当前目录。
- `--output PATH`：输出目录；默认是输入旁的 `x5_crop_output`。
- `--format`：`135`、`135-dual`、`half`、`xpan`、`120-645`、`120-66`、`120-67`。
- `--layout`：`auto`、`horizontal` 或 `vertical`。
- `--strip`：`full` 或 `partial`。
- `--count N`：partial 必填的明确曝光格数；包括中间空白曝光格，并且不能超过片夹容量。full
  使用格式固定张数。
- `--jobs N`：source 并发数；默认 1，上限 3。默认值优先控制一般电脑的峰值内存；内存充足且
  一次处理多张原 TIFF 时可显式使用 `--jobs 2`。数值库内部线程固定为 1。
- `--debug-analysis`：执行完整检测并生成自适应高度的三联诊断 JPG、报告、summary 和 manifest，
  但不写正式 TIFF，也不复制 `needs_review` 原图；默认关闭。完整片条保持原比例，不裁切照片。
  之后用相同输入和检测参数做普通运行时会自动尝试复用报告。
- `--allow-best-effort-output`：明确接受未验证文件系统的较弱发布语义。
- `--interactive`：交互选择格式、模式、张数和 Debug Analysis；无效的 partial count 会要求
  重新输入，直到有效或用户取消。

没有 `--overwrite`。一次成功运行总是以完整新结果替换上一套可确认归属的 V5 输出。

Debug Analysis 和正式裁切可分两步运行：

```bash
python3 X5_Crop.py /path/to/scans --format 120-66 --strip partial --count 2 --debug-analysis
python3 X5_Crop.py /path/to/scans --format 120-66 --strip partial --count 2
```

第一条命令在 `x5_crop_output/` 中只发布 Debug Analysis 和报告类文件。第二条命令会自动读取
其中的 `x5_crop_report.jsonl`；只有 current schema 与完整性哈希、程序版本、原 TIFF 的文件身份
与 profile、完整检测配置和 resolved layout 全部匹配时才跳过检测。任一项不一致就自动重新
检测。复用报告只省略检测、物理求解与 Gate；正式 TIFF 仍从原图写出并复读验证。

## 状态与退出码

每个输入只有一个终态：

- `approved_auto`：普通运行写出完整正式照片 TIFF；Debug Analysis 运行只记录 Gate 已通过。
- `needs_review`：普通运行不写正式照片，将原扫描件复制到 `needs_review/`；Debug Analysis 运行
  只记录原因。
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
有内容时出现。Debug Analysis 运行发布到同一个 `x5_crop_output/`，其中只有诊断 JPG、报告、
summary 和 manifest，没有正式 TIFF 或 review copy。

新运行先在输出目录旁建立完整内部事务目录。全部输入处理结束、正式 TIFF 复读通过、报告和
manifest 完整后，程序用两次同父目录 rename 发布新结果，再删除旧结果。程序异常或强制结束
后会在状态明确时恢复；突然断电造成状态歧义时保留 target、new、old 和 journal，要求人工
确认，绝不自动删除。若事务恢复、rename、发布或回滚失败，程序同样保留全部候选并以退出码
`3` 停止；此时不承诺旧输出已经回到原位置。

只有固定 owner marker、current manifest 和完整 inventory 全部匹配的旧目录才能自动替换。
额外文件、缺失文件、链接、junction、reparse point、旧 schema 或人工目录都会使程序停止。

## 文件系统与磁盘空间

APFS、HFS+ 与 NTFS 是 V5 事务模型的本地验证目标；是否已正式通过由对应版本的实机 receipt
证明，不由文件系统名称本身保证。SMB、NAS、云盘同步目录、没有自身 receipt 的 exFAT 或
无法确认语义的文件系统属于 best effort：

- 交互运行显示风险和目标路径，默认拒绝；
- 非交互 CLI 必须明确加入 `--allow-best-effort-output`。

该选择不能绕过锁、同文件系统、rename、路径安全或磁盘空间硬失败。运行前会为完整新结果、
报告、可选 Debug Analysis、事务开销和 32 MiB guard 做 invocation-wide 预算；旧结果在发布
成功前继续占用空间。

## TIFF 保真与隐私

正式 TIFF 仅由 `tifffile + imagecodecs` 读写。每张输出关闭写句柄后都会重新打开，并检查
16-bit RGB、三通道、contiguous planar、形状、像素、ICC、resolution、resolution unit、受支持
metadata、无损压缩与 `Orientation=1`。

普通运行与报告复用都不额外计算原 TIFF 的内容 SHA，也不检查 Git、黄金样片或性能 receipt，
不启用 profiler 或故障注入。Pillow 只在用户明确启用 Debug Analysis 时延迟导入。

## 移除与许可

卸载依赖：

- macOS：`install/X5_Crop_Mac_uninstall.command`
- Windows：`install/X5_Crop_win_uninstall.bat`

卸载器只删除由 X5 Crop 引入、版本未变化且不再被其它 package 需要的依赖。

License: MIT — [LICENSE](../LICENSE)
