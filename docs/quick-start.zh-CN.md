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

- `full`：用户确认片条采用匹配片夹的完整铺满布局；程序自动使用该片夹的完整曝光格数。
- `partial --count N`：片条没有铺满；`N` 是实际曝光格数，包括中间空白格，允许
  `1 <= N <= full_count`。Full 不接受 `--count`。
- `135-dual`：只允许 full，总计 12 格、每 lane 6 格。
- `--layout auto`：按扫描方向选择水平或垂直；也可明确指定。
- `--debug-analysis`：只生成 Debug Analysis JPG 和报告类文件，不写正式 TIFF 或 review copy；
  默认关闭。

程序不从文件名或像素猜 count，也不自动删除空白 slot。Partial 即使与 full_count 张数相同，也
不会获得铺满布局的长轴居中权限。Partial 缺 count、count 非正数、full 携带 count，或匹配后
partial count 大于完整张数，都会
在 detector 前以退出码 `2` 停止。交互式多文件运行会检查整批片夹/count；存在冲突时列出全部
冲突并返回模式/count 步骤。
片夹或物理位置无法唯一确定时进入 `needs_review`，不会猜测并输出 TIFF。

要先看检测结果再裁切，分别指定两个全新的输出目录：

```bash
python3 X5_Crop.py /path/to/scans --format 135 --strip full --debug-analysis --output /path/to/x5_debug
python3 X5_Crop.py /path/to/scans --format 135 --strip full --output /path/to/x5_crops
```

普通运行始终从原 TIFF 重新检测，不复用 Debug report。输出目录必须尚不存在。

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

`needs_review/` 和 `_debug_analysis/` 只在有内容时建立。运行先在目标同父目录写临时结果，完成后
一次发布；目标已存在时停止，绝不覆盖或删除。写盘、空间不足或 rename 失败会清理本次未发布的
临时目录并报告错误。

完整说明见 [中文用户手册](user-guide.zh-CN.md)。
