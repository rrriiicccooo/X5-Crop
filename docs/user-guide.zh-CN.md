# X5 Crop 用户手册

- 当前公开稳定版本：v4.2.8
- 仓库当前源码：V5 current-only，尚未公开发布
- 输入定位：用户已经知道 format、片条模式及必要 count 的 Hasselblad / Imacon X5 片夹扫描

## 产品行为

X5 Crop 的目标是自动产生足够安全且不切掉真实照片内容的 TIFF。用户提供胶片格式；程序使用
扫描像素、固定物理尺寸、片夹画布、张数与顺序共同判断。只有内容保护、多余边缘限制、变换和
TIFF 写出均成立时才输出正式照片，否则整张 source 进入 `needs_review`，不做部分 slot 挽救。

程序不承诺恢复唯一的真实照片边界，也不从文件名猜 format 或 count。程序先从图像独立匹配
片夹，再取得该片夹合同的完整曝光格数。Full 表示用户确认胶片采用片夹的完整铺满布局，程序自动
使用该格数；partial 表示没有铺满，必须输入实际 count，包括中间空白曝光格。Partial 允许与
`full_count` 相同的照片数，但不会使用片夹长轴居中和均匀排布事实。程序不删除空白 slot。例如
三张 120-66 既可以是铺满布局的 full，也可以是未铺满的 `partial --count 3`。

语法检查会拒绝 partial 缺少 count、count 非正数或 full 携带 count。匹配片夹后，如果 partial
count 大于实际 `full_count`，非交互整批调用同样在 detector 前以退出码 `2` 停止；交互启动器
列出全部冲突并返回模式/count 步骤，不要求重新选择 format 或 Debug Analysis，也不会逐 source
临时改写 count。图像不能唯一匹配片夹时保持 `needs_review`，不猜片夹或格数。`135-dual` 只允许
full，总计 12 格、每 lane 6 格。

正常间隙是两种模式共同的默认状态。程序先按 format 放下固定模板，再用至少两个独立 adjacency
校准当前片条的 source pitch；已支持的模板可以补全看不见的 separator，并明确标记为推导位置。
Full 不会把 format gap 搜索值变成定位事实，也不会用铺满布局覆盖接触、叠片或大间隙的直接证据。
局部异常必须由已经绑定到具体 adjacency 的直接 separator 证明，只让后续照片整体移动一次。

Format 决定照片矩形的物理尺寸。检测只负责根据片条方向、照片上下边缘、照片间黑带、共同尺寸
和局部卷片关系放置这些矩形，再把边缘测量所需的最小安全范围纳入输出。最终每一边都必须通过
以 format 尺寸为基准的 5%（start/end）或 3%（top/bottom）限制。相邻照片接触或重叠时，
相邻输出可以重复包含同一段 source pixels；这不是额外边缘，也不会改变照片数。

“保护内容”不等于裁切线外绝对不能出现任何内容像素。只发生在两条相邻边交角处的极小擦边、
锯齿或尘点保持中性；只有离开角落、连续跨过整条边界不确定区间的可靠二维画面才会否决自动裁切。
程序不会为了保留一个已确认可接受的角点而扩大或扭曲固定 format 框。

完整格数为：135=6、half=12、XPan=3、120-645=4、120-66=3；120-67 普通片夹为 3、短片夹
为 2。135-dual 总计 12 格，每 lane 6 格。

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
- `--count N`：仅 partial 使用且必填的正整数曝光格数；包括中间空白曝光格，不能超过匹配片夹
  的完整张数。Full 不接受 `--count`。照片数等于 `full_count` 时仍按实际布局选择模式：铺满用
  full，未铺满用 partial。`135-dual` 不接受 partial。
- `--jobs N`：source 并发数；默认 1，上限 3。默认值优先控制一般电脑的峰值内存；内存充足且
  一次处理多张原 TIFF 时可显式使用 `--jobs 2`。数值库内部线程固定为 1。
- `--debug-analysis`：执行完整检测并生成自适应高度的三联诊断 JPG、development report 和 summary，
  但不写正式 TIFF，也不复制 `needs_review` 原图；默认关闭。完整片条保持原比例，不裁切照片。
- `--interactive`：交互选择格式、模式、张数和 Debug Analysis；多文件的片夹/count 检查针对
  整批执行，存在冲突时列出全部冲突并返回模式/count 步骤。

没有 `--overwrite`。输出目录必须是一个尚不存在的新路径；程序不接管或删除旧输出。

Debug Analysis 和正式裁切可分两步运行：

```bash
python3 X5_Crop.py /path/to/scans --format 120-66 --strip partial --count 2 --debug-analysis
python3 X5_Crop.py /path/to/scans --format 120-66 --strip partial --count 2
```

两条命令必须使用不同的全新 `--output` 路径。Debug Analysis 只发布诊断与开发事实；普通运行始终
从原 TIFF 重新执行测量、物理求解和 Gate，不把旧 report 当作可执行状态。

## 状态与退出码

每个输入只有一个终态：

- `approved_auto`：普通运行写出完整正式照片 TIFF；Debug Analysis 运行只记录 Gate 已通过。
- `needs_review`：普通运行不写正式照片，将原扫描件复制到 `needs_review/`；Debug Analysis 运行
  只记录原因。
- `runtime_error`：该输入失败，不写它的照片；其它输入继续处理。

无法区分候选片夹、producer 上限被触发、不同最终裁切位置没有唯一物理胜出者，或可靠内容否决
所有位置时，结果均保持 `needs_review`，不输出猜测的照片 TIFF。普通 JSONL report 保存匹配片夹、
count authority、最终选择、安全范围与 Gate 根因；显式 Debug Analysis 额外保存模板位置、实际
observation、fit winner/runner、偏差与推导 ledger、内容否决和工作量 receipt。

退出码：

- `0`：成功发布，且没有 `runtime_error`。
- `1`：成功发布但含 `runtime_error`，或全部输入失败且未发布。
- `2`：命令行、输入集合或运行前检查失败。
- `3`：全新输出目录无法安全发布。

如果全部输入均为 `runtime_error`，程序不发布空结果，上一套输出保持不动。

## 输出与安全发布

默认结构：

```text
x5_crop_output/
  原文件名_01.tif
  原文件名_02.tif
  needs_review/
  _debug_analysis/
  x5_crop_report.jsonl
  x5_crop_summary.csv
```

照片直接位于根部，不建立 `run-*` 或 source 子目录。`needs_review/` 和 `_debug_analysis/` 仅在
有内容时出现。Debug Analysis 使用自己指定的全新输出目录，其中只有诊断 JPG、report 与 summary，
没有正式 TIFF 或 review copy。

每次运行先在目标同父目录建立临时目录。全部输入处理、必要 TIFF header 检查和报告写完后，程序
用一次 rename 发布为目标目录。目标已存在或处理中出现同名目录时退出码为 `3`；程序不会遍历、
覆盖、接管或删除其中任何内容。写盘、空间不足或 rename 失败时清理本次未发布的临时目录并报告
实际错误，不维护隐藏的磁盘预留账本或恢复状态机。

## TIFF 保真与隐私

正式 TIFF 仅由 `tifffile + imagecodecs` 读写。每张输出关闭写句柄后会重新打开 header，并检查
16-bit RGB、三通道、contiguous planar、shape、ICC、resolution、resolution unit、受支持 metadata、
无损压缩与 `Orientation=1`。完整像素复读属于 TIFF contract、named-TIFF、platform、端到端与发布
验证，不让普通用户每张输出重复完整解码。

普通运行不额外计算原 TIFF 的内容 SHA，也不检查 Git、黄金样片或性能 receipt，
不启用 profiler 或故障注入。Pillow 只在用户明确启用 Debug Analysis 时延迟导入。

## 移除与许可

卸载依赖：

- macOS：`install/X5_Crop_Mac_uninstall.command`
- Windows：`install/X5_Crop_win_uninstall.bat`

卸载器只删除由 X5 Crop 引入、版本未变化且不再被其它 package 需要的依赖。

License: MIT — [LICENSE](../LICENSE)
