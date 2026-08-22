# X5 Crop V5 快速启动（开发预览）

本文只适用于仓库 `main` 的未发布 V5 开发源码。当前公开稳定版仍是 v4.2.8；普通用户请下载
Release 包并阅读包内随附的 v4.2.8 文档，不要把本文中的 V5 命令用于稳定版。

## 1. 安装

取得完整仓库源码后，在仓库根目录运行对应安装器：

- macOS：`tools/install/X5_Crop_Mac_install.command`
- Windows：`tools/install/X5_Crop_win_install.bat`

未来 V5 Release 包中的相同安装器位于 `install/`，不带 `tools/` 前缀。

安装器寻找 Python 3.12–3.14，复用合格依赖，只安装缺失项。Homebrew 不是前置条件，也不会建立
私有虚拟环境。

## 2. 放入 TIFF 并启动

把受支持的 X5 扫描 TIFF 与 V5 启动器放在同一文件夹：

- macOS：双击 `X5_Crop_Mac.command`
- Windows：双击 `X5_Crop_win.bat`

也可以从命令行运行：

```bash
python3 X5_Crop.py /path/to/scans --format 135
```

省略 `--count` 表示确认匹配片夹的默认格数。处理其它格数时明确输入：

```bash
python3 X5_Crop.py /path/to/scans --format 120-66 --count 2
```

Count 包括中间空白曝光格。程序不从文件名或画面猜张数，也不删除空白格。`135-dual` 的默认值是
12（每 lane 6）；明确输入其它值会进入人工检查，不猜两条 lane 的分配。

交互模式对所有 format 都会询问 count。直接回车表示确认匹配片夹的默认值；`135-dual` 也允许
输入其它数字，但除 12 外都会安全进入人工检查。

Deskew 默认只在批准后尝试小角度整理。要让输出保持原始方向：

```bash
python3 X5_Crop.py /path/to/scans --format 135 --deskew off
```

`--layout auto` 会判断水平或垂直扫描，也可明确指定。V5 接受受支持无损压缩的单页 16-bit RGB
TIFF；完整输入合同见[中文用户手册](user-guide.zh-CN.md)。

## 3. 先看 Debug Analysis

要先检查检测结果再正式裁切，请使用两个不同且尚不存在的输出目录：

```bash
python3 X5_Crop.py /path/to/scans --format 135 --debug-analysis --output /path/to/x5_debug
python3 X5_Crop.py /path/to/scans --format 135 --output /path/to/x5_crops
```

Debug Analysis 只生成诊断 JPG 和报告，不写正式照片或 review copy。普通运行始终从原 TIFF 重新
检测，不复用 Debug report。

## 4. 查看结果

```text
x5_crop_output/
  原文件名_01.tif
  原文件名_02.tif
  needs_review/
  _debug_analysis/
  x5_crop_report.jsonl
  x5_crop_summary.csv
```

程序只会整体批准一张 source：任一格不安全，整张 source 都进入 `needs_review`。目标目录已经
存在时程序停止，不会覆盖或删除。Deskew 是安全决定之后的可选整理；关闭、无法稳定测量或角度
超过小整理范围时仍会输出安全照片，只保留原始倾斜。旋转输出的外包矩形角落可能为黑色。完整说明见
[中文用户手册](user-guide.zh-CN.md)。
