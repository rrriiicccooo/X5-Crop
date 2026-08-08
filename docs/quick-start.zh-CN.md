# X5 Crop 快速启动

当前公开稳定版是 v4.2.8；本仓库中的 V5 尚未发布。发布包请从 GitHub Releases 下载
`X5-Crop-vX.X.zip`，不要使用自动生成的 Source code 压缩包。

## 1. 安装

解压发布包后运行对应安装器：

- macOS：`install/X5_Crop_Mac_install.command`
- Windows：`install/X5_Crop_win_install.bat`

安装器先寻找 Python 3.12–3.14，再复用所有版本已经满足的依赖，不区分 Homebrew、pip 或其它
来源。缺失项才安装到该 Python 的用户级 site；版本不符时只通过能够确认的原 package manager
更新，未知来源会安全停止而不叠加第二份包。Homebrew 不是必需项，也不会仅为 OpenCV 被强制
安装。不建立私有虚拟环境，因此 `X5_Crop.py` 可放在任意文件夹运行。

## 2. 放入 TIFF 并启动

把受支持的 X5 扫描 TIFF 与启动器放在同一文件夹：

- macOS：双击 `X5_Crop_Mac.command`
- Windows：双击 `X5_Crop_win.bat`

也可以从命令行运行：

```bash
python3 X5_Crop.py /path/to/scans --format 135 --strip full
```

V5 输入必须是单页、16-bit unsigned、RGB、三通道、contiguous planar 且使用受支持无损压缩的
TIFF。其它结构会安全失败，不会猜测。

## 3. 选择格式、模式与张数

- `full`：使用该格式的固定片夹张数。
- `partial --count N`：`N` 是用户明确给出的输出张数。
- `partial --count auto`：保守输出匹配片夹对该格式的全部有效 slots，可能包含空白 TIFF。
- `--layout auto`：按扫描方向选择水平或垂直；也可明确指定。
- `--debug-analysis`：显式生成诊断 JPG；默认关闭。

程序不从文件名猜 format 或 count，也不自动删除空白 slot。

## 4. 查看结果

成功运行后，照片直接位于 `x5_crop_output/` 根部：

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

`needs_review/` 和 `_debug_analysis/` 只在有内容时建立。每次成功运行会用完整新结果替换上一套
可确认由 X5 Crop V5 创建的结果；旧目录含未知文件时程序停止，绝不擅自删除。

APFS、HFS+ 与 NTFS 是本地事务验证目标，但正式支持仍以对应版本的实机 receipt 为准。
在未验证文件系统上，交互启动会询问是否继续；非交互命令行必须明确加入
`--allow-best-effort-output`。该选项不能绕过锁、路径、磁盘空间或 rename 的硬失败。

完整说明见 [中文用户手册](user-guide.zh-CN.md)。
