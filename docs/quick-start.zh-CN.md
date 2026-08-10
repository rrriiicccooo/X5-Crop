# X5 Crop 快速启动

当前公开稳定版是 v4.2.8；本仓库中的 V5 尚未发布。发布包请从 GitHub Releases 下载
`X5-Crop-vX.X.zip`，不要使用自动生成的 Source code 压缩包。

## 1. 安装

解压发布包后运行对应安装器：

- macOS：`install/X5_Crop_Mac_install.command`
- Windows：`install/X5_Crop_win_install.bat`

安装器寻找 Python 3.12–3.14，并直接复用已满足版本合同的依赖。缺失项才安装；未知来源或无法
安全更新的环境会在改动前停止。Homebrew 不是前置条件，也不建立私有虚拟环境。

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
- `partial --count N`：`N` 是这段片条实际包含的曝光格数，包括中间空白曝光格；不能超过
  片夹容量。交互启动时输入无效会要求重新输入。
- `--layout auto`：按扫描方向选择水平或垂直；也可明确指定。
- `--debug-analysis`：只生成 Debug Analysis JPG 和报告类文件，不写正式 TIFF 或 review copy；
  默认关闭。

程序不从文件名或片夹容量猜 count，也不自动删除空白 slot。

要先看检测结果再裁切，连续运行同一组参数，第二次去掉 `--debug-analysis`：

```bash
python3 X5_Crop.py /path/to/scans --format 135 --strip full --debug-analysis
python3 X5_Crop.py /path/to/scans --format 135 --strip full
```

两次运行使用同一个 `x5_crop_output/`。第二次会自动验证并复用现有 report；只有 current schema、
完整性、程序版本、原 TIFF 身份与 profile、检测配置和 layout 全部匹配时才跳过检测，否则自动
重新检测。正式 TIFF 始终从原图写出并复读验证。

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

`needs_review/` 和 `_debug_analysis/` 只在有内容时建立。每次成功运行
会用完整新结果替换上一套可确认由 X5 Crop V5 创建的结果；旧目录含未知文件时程序停止，绝不
擅自删除。

APFS、HFS+ 与 NTFS 是本地事务验证目标，但正式支持仍以对应版本的实机 receipt 为准。
在未验证文件系统上，交互启动会询问是否继续；非交互命令行必须明确加入
`--allow-best-effort-output`。该选项不能绕过锁、路径、磁盘空间或 rename 的硬失败。

完整说明见 [中文用户手册](user-guide.zh-CN.md)。
