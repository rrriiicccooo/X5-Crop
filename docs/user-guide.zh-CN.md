# X5 Crop 用户手册

- 当前稳定发布：**v4.2.8**
- 仓库状态：V4.9 为架构实验；V5 是下一生产目标，尚未发布

X5 Crop 用于把 Hasselblad / Imacon X5 片夹扫描 TIFF 保守地拆成单张照片。你负责提供胶片
格式、片条模式和必要的张数；程序负责检测、deskew、安全裁切、TIFF 写出与复读验证。
本手册随仓库开发；正式使用请以 GitHub Release 包内文档为准。

## 产品行为

X5 Crop 的首要目标是不切掉真实照片内容，其次是避免输出宽到需要人工重裁。

- 程序把像素边缘与已知格式尺寸组合成少量完整照片摆放方案，不根据一条最高分边线盲目
  裁切。
- 多个同样成立的摆放会共同决定安全裁切。若无法在允许外扩内同时容纳，结果为
  `needs_review`。
- `start/end` 每边最大允许外扩为照片设计宽度的 5%；`top/bottom` 每边为设计高度的 3%。
  四边分别是硬上限，刚好达到上限仍可通过。
- 输出可以带少量边缘或邻片像素，相邻输出也可以重叠；完整保留照片内容优先。
- Partial auto 保留匹配片夹的全部有效 slots，因此可能写出可直接删除的 blank TIFF。程序
  不从文件名或画面外观猜真实照片张数。
- `approved_auto` 只表示最终输出满足当前安全合同，不表示程序唯一还原了真实物理边缘。

## 安装

从 [GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases) 下载
`X5-Crop-vX.X.zip`，不要下载 GitHub 自动生成的 Source code。解压后运行一次：

```text
macOS:   install/X5_Crop_Mac_install.command
Windows: install/X5_Crop_win_install.bat
```

安装器检查 `numpy`、`tifffile`、`imagecodecs` 和 `Pillow`。macOS 安装器只准备当前
Release 文件夹，不建立系统级信任。

将入口、启动器和 TIFF 放在同一文件夹：

```text
X5_Crop.py
X5_Crop_Mac.command 或 X5_Crop_win.bat
*.tif / *.tiff
```

macOS 双击 `X5_Crop_Mac.command`，Windows 双击 `X5_Crop_win.bat`。macOS 无法双击时，
在该文件夹的 Terminal 中运行：

```bash
/bin/bash X5_Crop_Mac.command
```

## 格式、模式与 count

| 输入 | 格式 | Full 张数 | Partial |
|---|---|---:|---|
| Return / `135` | 135 | 6 | 1..6 或 auto |
| `dual` / `135-dual` | 135 双 lane | 12 | 不支持 |
| `half` | 半格 | 12 | 1..12 或 auto |
| `xpan` | XPan | 3 | 1..3 或 auto |
| `645` / `120-645` | 120-645 | 4 | 1..4 或 auto |
| `66` / `120-66` | 120-66 | 3 | 1..3 或 auto |
| `67` / `120-67` | 120-67 | 3 | 1..3 或 auto |

Format 始终由用户提供，runtime 不自动猜格式。

- Full 使用格式默认张数。
- Partial 整数是权威 explicit count。
- Partial 省略 `--count`、输入 `--count auto` 或在交互模式直接回车，均使用片夹容量。
- Auto 先匹配片夹，再输出该片夹对当前格式的全部有效 slots；它不推断可见照片张数。
- `135-dual` 的输出顺序为第一个 lane 的 1..6，再到第二个 lane 的 1..6。

## 运行

普通 full：

```bash
python3 X5_Crop.py . --format 135 --strip full --report
```

Partial explicit 与 auto：

```bash
python3 X5_Crop.py . --format 135 --strip partial --count 3 --report
python3 X5_Crop.py . --format 120-66 --strip partial --count auto --report
```

显式指定垂直片条：

```bash
python3 X5_Crop.py . --format 120-66 --strip partial --layout vertical --report
```

`--layout auto` 为默认值。并发默认 `--jobs 2`；普通运行最多 3，诊断最多 4。完整参数见：

```bash
python3 X5_Crop.py --help
```

## 状态与人工检查

每个输入只有三类结果：

- `approved_auto`：安全检查通过，写出正式照片 TIFF。
- `needs_review`：存在明确风险，不写正式照片 TIFF；report 会记录原因。
- terminal error：读取、检测执行、写出或复读失败。它不是 review。

常见 review 情况包括：片夹或请求张数无法成立、完整格式摆放不足、deskew 方向不唯一、同一
source 的照片尺寸与尺度无法一致、输出超出 lane、无法包含所有保留摆放、任一边超过 5%/3%，
或 transform 无法安全建立。

默认会把需要 review 的原 TIFF 复制到 `needs_review/`。使用
`--no-copy-review-files` 可以关闭。

## 输出与诊断

默认输出目录为：

```text
x5_crop_output/
  原文件名_01.tif
  原文件名_02.tif
  ...
  needs_review/
  _debug_analysis/
  x5_crop_report.jsonl
  x5_crop_summary.csv
  x5_crop_run_manifest.jsonl
```

只有启用相应选项时才会生成附加文件：

- `--report`：写 JSONL 详细记录和 CSV 摘要。
- `--debug-analysis`：写四层诊断 JPG，展示片夹权限、像素证据、照片摆放与最终安全输出。
- `--diagnostics`：只读诊断；自动启用 report 和 Debug Analysis，不写照片 TIFF，也不复制
  review 文件。
- `--overwrite`：允许覆盖已存在的输出。
- `--compression same`：尽量保持已支持的源无损压缩；`none` 写无压缩 TIFF。

## TIFF 保真

原 TIFF 永不修改。每个批准输出只从原图执行一次 inverse-affine sampling；lane 外的插值
像素使用背景，不会采入另一个 lane。写出后立即复读并检查：

- dtype、位深、axes、shape、通道与 planar configuration；
- photometric、ICC/色彩空间；
- resolution 与 resolution unit；
- description、datetime、software 和受支持 metadata；
- 像素与无损压缩行为。

任何读取、写出、原子替换或复读失败都会留下独立错误，不会生成成功结果。

## 当前验证边界

V4.9 只作为 fixed-format template-first 架构实验保留。V5 尚未完成实现、真实照片准确率与
发布验证。请使用 GitHub Releases 中标记的稳定版本处理重要原片，并保留原 TIFF。

## 移除与许可

删除 X5 Crop 文件夹即可移除程序和本地输出。安装的 Python packages 可能被其它程序共用，
因此不提供批量卸载脚本。

许可证：MIT。发布包根目录包含 `LICENSE`；GitHub 也提供
[完整文本](https://github.com/rrriiicccooo/X5-Crop/blob/main/LICENSE)。
