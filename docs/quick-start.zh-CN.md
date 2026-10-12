# X5 Crop V5 快速启动（开发预览）

本文只适用于仓库 `main` 的未发布 V5 开发源码。当前公开稳定版是 v4.2.8；普通用户请下载 Release 包并
阅读包内随附的对应文档。

## 安装

取得完整仓库源码后，在仓库根目录运行对应安装器：

- macOS：`tools/install/X5_Crop_Mac_install.command`
- Windows：`tools/install/X5_Crop_win_install.bat`

未来 V5 Release 包中的相同安装器位于 `install/`，不带 `tools/` 前缀。安装器寻找 64-bit Python 3.12–3.14，
复用符合版本要求的依赖，并补齐或更新其余依赖。Homebrew 不是前置条件，也不会建立私有虚拟环境。

## 运行一张 source

在仓库根目录运行命令，输入可以是一个 TIFF 或扫描目录，并提供已知 format：

```bash
python3 X5_Crop.py /path/to/scans --format 135
```

省略 `--count` 表示确认匹配片夹的默认完整格数。处理其它已知格数时明确输入：

```bash
python3 X5_Crop.py /path/to/scans --format 120-66 --count 2
```

首次检查先使用新的 Debug 目录，再使用另一个新的目录正式裁切：

```bash
python3 X5_Crop.py /path/to/scans --format 135 --debug-analysis --output /path/to/x5_debug
python3 X5_Crop.py /path/to/scans --format 135 --output /path/to/x5_crops
```

Debug Analysis 只生成诊断 JPG 和报告，不写正式 TIFF。正式运行重新读取原 TIFF，不复用 Debug report。
目标目录必须不存在；若目标已存在，程序保留它并报告输出错误。

## 查看结果

```text
x5_crop_output/
  原文件名_01.tif
  原文件名_02.tif
  needs_review/
  _debug_analysis/
  x5_crop_report.jsonl
  x5_crop_summary.csv
```

程序按 source 整体批准：任一必需 slot 不安全或证据不足，整张 source 都进入 `needs_review`。Deskew 是安全
决定之后的可选整理。完整输入合同、format/count、几何、输出细节和退出码见[中文用户手册](user-guide.zh-CN.md)。
