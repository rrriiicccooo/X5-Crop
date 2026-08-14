# X5 Crop 快速启动

当前公开稳定版是 v4.2.8；本仓库中的 V5 尚未发布。请从 GitHub Releases 下载
`X5-Crop-vX.X.zip`，不要使用自动生成的 Source code 压缩包。

## 1. 安装

解压发布包后运行对应安装器：

- macOS：`install/X5_Crop_Mac_install.command`
- Windows：`install/X5_Crop_win_install.bat`

安装器寻找 Python 3.12–3.14，复用合格依赖，只安装缺失项。来源不明或无法安全更新时会在改动前
停止。Homebrew 不是前置条件，也不会建立私有虚拟环境。

## 2. 放入 TIFF 并启动

把受支持的 X5 扫描 TIFF 与启动器放在同一文件夹：

- macOS：双击 `X5_Crop_Mac.command`
- Windows：双击 `X5_Crop_win.bat`

也可以从命令行运行：

```bash
python3 X5_Crop.py /path/to/scans --format 135 --strip full
```

V5 接受受支持无损压缩的单页 16-bit RGB TIFF。完整输入合同见
[中文用户手册](user-guide.zh-CN.md)。

## 3. 选择格式、模式与张数

- `full`：片条采用匹配片夹的完整铺满布局，程序自动使用完整格数。
- `partial --count N`：片条没有铺满；`N` 是实际曝光格数，包括中间空白格。
- `135-dual`：只允许 full，总计 12 格、每 lane 6 格。
- `--layout auto`：按扫描方向选择水平或垂直；也可明确指定。
- `--debug-analysis`：只生成诊断 JPG 和报告，不写正式照片或 review copy。

程序不从文件名或像素猜 count，也不删除空白 slot。Partial 即使与完整格数相同，也不获得 full
的居中权限。片夹或照片位置无法唯一确定时进入 `needs_review`，不会猜测输出。

要先看检测结果再裁切，分别指定两个全新的输出目录：

```bash
python3 X5_Crop.py /path/to/scans --format 135 --strip full --debug-analysis --output /path/to/x5_debug
python3 X5_Crop.py /path/to/scans --format 135 --strip full --output /path/to/x5_crops
```

普通运行始终从原 TIFF 重新检测，不复用 Debug report；输出目录必须尚不存在。

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
```

`needs_review/` 和 `_debug_analysis/` 只在需要时建立。目标目录已存在时程序停止，不会覆盖或删除。

完整说明见 [中文用户手册](user-guide.zh-CN.md)。
