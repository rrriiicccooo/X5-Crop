# X5 Crop 用户手册

- 当前开发版本：**V4.9 source-core 安全基线**
- 当前稳定发布：**v4.2.8**

当前 V4.9 开发版读取 X5 片夹扫描 TIFF，建立 scan-canvas、分轴尺度与 positive-content
审计，并生成复核副本、报告和 Debug Analysis。因为尚无获批的独立 Frame Grid phase
authority，所有输入都保持 `needs_review`，不导出单张 frame TIFF。

这不是自动裁切失败后的 fallback，而是当前版本的正式能力边界。

## 产品目标

X5 Crop 的自动裁切目标是“足够安全且不切掉真实照片内容”，不是唯一测量照片边界。用户
提供的 format 与 count 是输入前提；未来 Grid/output flow 可以结合已观测线索与格式模型
推断位置，并用毫米 protection 保守向外多留像素。

`approved_auto` 将表示保护后的输出满足安全合同，不表示每条 separator、照片边或 Grid
phase 都被唯一证明。只有具体且无法被 protection 吸收的错格、照片归属或 inward content
loss 风险才应进入 `needs_review`。保护后的相邻输出可以重叠，也可以包含相邻照片像素；
这不等于 primary slot ownership 错误。当前 V4.9 尚未实现这套 flow，所以仍保持下述
全量 review 行为。

## 安装

从 [GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases) 下载
`X5-Crop-vX.X.zip`，不要下载 GitHub 自动生成的 Source code。

首次运行对应安装器：

```text
macOS:   install/X5_Crop_Mac_install.command
Windows: install/X5_Crop_win_install.bat
```

安装器检查或安装 `numpy`、`tifffile`、`imagecodecs` 和 `Pillow`。macOS
安装器只处理当前 Release 文件夹的权限和 quarantine，不建立系统级信任。

将入口、启动器和 TIFF 放在同一文件夹：

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

## 格式与模式

| 输入 | 格式 | Full 设计张数 |
|---|---|---:|
| Return / `135` | 135 | 6 |
| `dual` / `135 dual` / `135-dual` | 135 双条 | 12 |
| `half` | 半格 | 12 |
| `xpan` | XPan | 3 |
| `645` | 120-645 | 4 |
| `66` | 120-66 | 3 |
| `67` | 120-67 | 3 |

- Full 与 partial 使用同一个完整 scan-canvas/lane 短轴 domain。
- Partial count 只描述若干张完整设计 slot，不表示残缺照片。
- 用户提供的 count 与格式是未来自动裁切的 authoritative input；当前版本只把它们写入
  审计身份，尚不生成 frame。
- `135-dual` 分 lane 审计并固定保持 review。

## 当前检测事实

每个 TIFF 只建立一次 base gray 和 image statistics。已知 scan canvas 必须从像素长短比
唯一匹配；无匹配或多个 profile 同时成立都保持 review。

当前 scan-canvas catalog 使用下列长轴 × 短轴尺寸：

| Profile | 物理尺寸 | 适用格式与最大张数 |
|---|---:|---|
| `135_standard` | `232 × 32.22 mm` | 135 ≤ 6；half ≤ 12；XPan ≤ 3 |
| `135_narrow` | `232 × 25.4 mm` | 135 ≤ 6；half ≤ 12；XPan ≤ 3 |
| `135_dual` | `232 × 63.44 mm` | 135-dual ≤ 12 |
| `120_standard` | `226 × 60 mm` | 645 ≤ 4；66 ≤ 3；67 ≤ 3 |
| `120_wide_224_5` | `224.5 × 63.44 mm` | 645 ≤ 4；66 ≤ 3；67 ≤ 3 |
| `120_wide_223` | `223 × 63.44 mm` | 645 ≤ 4；66 ≤ 3；67 ≤ 3 |
| `120_wide_188_5` | `188.5 × 63.44 mm` | 645 ≤ 4；66 ≤ 3；67 ≤ 2 |

Format 与 resolved count（full 默认张数或显式 partial count）先排除物理上装不下的
profile，再做长宽比匹配；不会选择“最近 profile”。135-dual 先按完整
`232 × 63.44 mm` 画布建立 scale，再从中心分成两个 lane。

Long/short px/mm 分别计算，互不扩宽。TIFF DPI/PPI 只作为输出 metadata 保存，不参与
检测。

Positive content 使用两份独立 field：

```text
intensity = abs(I - five_point_local_mean(I)) / 255
texture   = (abs(dx) + abs(dy)) / 510
positive  = intensity_supported AND texture_supported
```

组件使用严格 4-connectivity 和只读 RLE 保存。它只能描述 source content，不能创建
frame phase、separator、照片边或 deskew。

当前 Grid outcome 固定为：

```text
NO_INDEPENDENT_PHASE_AUTHORITY
```

因此：

- 状态：`needs_review`
- 原因：`frame_grid_authority_unavailable`
- containment：`NOT_APPLICABLE_FRAME_GRID_UNAVAILABLE`
- visual deskew：`NOT_APPLICABLE_CORE_UNAVAILABLE`
- frame outputs：空

如果 scan canvas 或 content measurement 本身不可用，报告会追加独立 typed reason。

## 运行与输出

普通命令：

```bash
python3 X5_Crop.py . --format 135 --strip full --report
```

诊断命令：

```bash
python3 X5_Crop.py . --format 135 --strip full --diagnostics
```

完整参数：

```bash
python3 X5_Crop.py --help
```

默认使用 `--jobs 2`。当前输出目录可能包含：

```text
x5_crop_output/
  needs_review/
  _debug/
  _debug_analysis/
  x5_crop_report.jsonl
  x5_crop_summary.csv
  x5_crop_run_manifest.jsonl
```

- `needs_review/` 默认保存原始 TIFF 副本；`--no-copy-review-files` 可关闭复制。
- `--report` 写 current-only JSONL/CSV。
- `--debug-analysis` 写 domain 与 positive-content 的有界可视化摘要。
- `--diagnostics` 等价于 report + Debug Analysis + 不复制复核文件。
- 原始 TIFF 永不修改。

Current schema：

```text
schema_id       = detection_report
schema_revision = source_core_grid_authority
```

报告中的 typed configuration 会保存 `resolved_frame_count`，并列出经过该 count 容量过滤后
参与匹配的 scan-canvas profiles。

旧 `--bleed`、`--bleed-x`、`--bleed-y`、`--export-review` 与 `--dry-run` 已删除，
传入时会被拒绝。格式级毫米 protection authority 只记录于报告；没有 frame geometry 时
不会应用，也没有用户 override。

## ROI/TIFF foundation

虽然 current runtime 不导出 frame，inverse-affine ROI 与 TIFF writer 仍作为独立 foundation
保留并验证：

- identity 为精确半开切片；
- affine ROI 与 test reference 逐像素一致；
- 原始 RGB 每个 ROI 只采样一次；
- 保持 dtype、axes、ICC、resolution、metadata 与 NONE/LZW compression；
- 越界直接报错，不 clamp。

这些 foundation contracts 不等于当前已具备自动裁切能力。

## 性能声明边界

当前固定 24 张 detector-only 诊断只有在 `--jobs 2`、三次中位数严格小于
`5.0 秒/张`时，才能说明仍有未来生产余量。它不是正式输出性能 PASS。

24 张真实 frame TIFF 写出、复读和 `<=5.0 秒/张`的认证，要等 bounded Grid proposal 与
safe crop envelope 恢复自动输出后才能执行。当前认证状态必须是 `not_certified`。

## 卸载与许可

删除 X5 Crop 文件夹即可移除程序和该文件夹中的输出。卸载器只清理用户级 Python 依赖，
不会删除 Python；这些依赖也可能被其它工具使用。

```text
macOS:   install/X5_Crop_Mac_uninstall.command
Windows: install/X5_Crop_win_uninstall.bat
```

许可证：MIT。完整文本见
[GitHub LICENSE](https://github.com/rrriiicccooo/X5-Crop/blob/main/LICENSE)。
