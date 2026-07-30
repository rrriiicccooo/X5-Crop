# X5 Crop 快速启动

本页适用于 V4.9 当前开发版。X5 Crop 在用户指定胶片格式后执行保守自动裁切：优先完整
保留真实照片内容，允许输出向外多留、相邻框重叠或带入少量邻片像素，不追求贴边复刻。
当前稳定发布仍为 **v4.2.8**。

## 1. 下载与安装

从 [GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases) 下载
`X5-Crop-vX.X.zip`，不要下载 GitHub 自动生成的 Source code。解压后运行一次：

```text
macOS:   install/X5_Crop_Mac_install.command
Windows: install/X5_Crop_win_install.bat
```

安装器准备 `numpy`、`tifffile`、`imagecodecs` 与 `Pillow`。

## 2. 放入 TIFF 并启动

```text
X5_Crop.py
X5_Crop_Mac.command 或 X5_Crop_win.bat
*.tif / *.tiff
```

```text
macOS:   双击 X5_Crop_Mac.command
Windows: 双击 X5_Crop_win.bat
```

macOS 无法双击时，在该文件夹的 Terminal 中运行：

```bash
/bin/bash X5_Crop_Mac.command
```

## 3. 选择格式、模式和张数

支持 `135`、`135-dual`、`half`、`xpan`、`645`、`66` 与 `67`。

- `full`：张数固定为格式默认值；若显式输入 count，只接受同一个默认值。
- `partial`：输入整数表示 authoritative explicit count；直接回车、输入 `auto`，或命令行
  省略 `--count`，都表示容量 auto。
- Auto 输出唯一匹配片夹对当前 format 的全部有效 slots，不猜真实照片张数，也不读取
  文件名中的张数。前导、尾随或中间 blank slot 都会保留。
- `135-dual` 当前只支持 full，按上 lane 后下 lane、各 lane 从左到右输出 12 张。

命令行示例：

```bash
python3 X5_Crop.py . --format 135 --strip full --report
python3 X5_Crop.py . --format 135 --strip partial --count 3 --report
python3 X5_Crop.py . --format 135 --strip partial --count auto --report
python3 X5_Crop.py . --format 120-66 --strip partial --layout vertical --report
```

默认使用 `--jobs 2`。普通运行可显式使用 `--jobs 3`，但会增加峰值内存压力；诊断模式
最多使用 4 个 worker。查看全部参数：

```bash
python3 X5_Crop.py --help
```

## 4. 结果与输出

`approved_auto` 表示 protection 后的输出满足有界安全合同；它不表示每条照片边或
separator 都被唯一证明。通过时会生成：

```text
x5_crop_output/
  原文件名_01.tif
  原文件名_02.tif
  ...
  x5_crop_report.jsonl
  x5_crop_summary.csv
  x5_crop_run_manifest.jsonl
```

`needs_review` 只表示存在具体且无法吸收的 ordinal、slot ownership、omission coverage、
已知内容 containment、source/lane authority 或 output geometry 风险。容量已解析但无法
精确形成全部 slots 时也会阻断。默认把原 TIFF 复制到
`needs_review/`；`--no-copy-review-files` 可关闭。

`--diagnostics` 是只读诊断模式：保留同一检测与 DecisionGate 结果，写 report 和
Debug Analysis，但不写 frame TIFF，也不复制 review 文件。

## 5. TIFF 安全

- 原始 TIFF 永不修改。
- 每个输出 ROI 只从原图采样一次，随后写出并复读验证。
- 保持 dtype、axes、通道、ICC/色彩空间、resolution、metadata，以及 NONE/LZW
  无损压缩行为。
- I/O 或复读失败是独立 terminal failure，不会伪装成 `needs_review`。

## 6. 移除

删除 X5 Crop 文件夹即可移除程序。Python packages 可能被其它程序共用，因此发布包不提供
批量依赖卸载脚本。
