# X5 Crop 用户手册

- 当前开发版本：**V4.9 bounded safe crop**
- 当前稳定发布：**v4.2.8**

X5 Crop 用于保守裁切 Hasselblad / Imacon X5 片夹扫描 TIFF。用户先提供 format；系统在
片夹物理容量、有限 Grid 搜索和向外安全包络内确定 frame，并在安全合同成立时写出单张
TIFF。

## 产品目标

完成标准是“不切掉真实照片内容”，不是唯一测量真实物理边界：

- `approved_auto` 表示最终 protection 后的输出满足有界安全合同。
- 输出可以比照片更大，相邻输出可以重叠，也可以带入少量邻片像素。
- Separator 缺失、blank、inferred Grid、等价 geometry、未 deskew 或 protection 在
  authority 边界饱和，都不会单独导致 review。
- `needs_review` 只用于无法吸收的具体风险，例如 count 竞争、ordinal 或 primary slot
  ownership 无法有界、已知内容可能被内切，或 geometry 越出 source/lane authority。
- 读取、写出或复读失败属于 terminal failure，不是 `needs_review`。

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

```text
macOS:   双击 X5_Crop_Mac.command
Windows: 双击 X5_Crop_win.bat
```

macOS 无法双击时，在该文件夹的 Terminal 中运行：

```bash
/bin/bash X5_Crop_Mac.command
```

## 格式、模式与 count

| 输入 | 格式 | Full 张数 | Partial |
|---|---|---:|---|
| Return / `135` | 135 | 6 | 1..6 或 auto |
| `dual` / `135 dual` / `135-dual` | 135 双条 | 12 | 不支持 |
| `half` | 半格 | 12 | 1..12 或 auto |
| `xpan` | XPan | 3 | 1..3 或 auto |
| `645` | 120-645 | 4 | 1..4 或 auto |
| `66` | 120-66 | 3 | 1..3 或 auto |
| `67` | 120-67 | 3 | 1..3 或 auto |

Format 始终由用户提供，runtime 不自动猜格式。

Count 入口规则只有一套：

- Full 规范化为 `fixed_full`；显式 count 只接受该格式的默认张数。
- Partial 输入整数时为 authoritative `explicit`。
- Partial 在命令行省略 `--count`、输入 `--count auto`，或交互时直接回车，均为 `auto`。
- 没有独立 `--auto-count` 参数。
- Auto 只搜索 `1..default_count`，再由唯一匹配片夹的容量排除装不下的 count。
- 文件名中的 `X5_<count>` 只可用于 validation，不会进入 detector、prior、score、
  Gate 或 runtime selection。

Partial count 表示完整设计 slot 的数量，不表示残缺照片。Blank 仍保留对应 slot。
`135-dual` 先匹配完整画布，再分为两个 canonical lane；输出顺序为上 lane 1..6、下 lane
1..6。

## 运行

普通命令：

```bash
python3 X5_Crop.py . --format 135 --strip full --report
```

Partial explicit：

```bash
python3 X5_Crop.py . --format 135 --strip partial --count 3 --report
```

Partial auto：

```bash
python3 X5_Crop.py . --format 120-66 --strip partial --count auto --report
```

垂直片条可以显式指定：

```bash
python3 X5_Crop.py . --format 120-66 --strip partial --layout vertical --report
```

`--layout auto` 是默认值。并发默认 `--jobs 2`；普通运行可显式提高到最多 3 个 worker，
诊断最多 4 个。`--jobs 3` 适合内存充足且一次处理至少三张 TIFF 的机器；它会提高峰值
内存压力，因此不作为默认值。正式性能认证仍固定使用 `--jobs 2`。

```bash
python3 X5_Crop.py --help
```

## 检测与安全包络

每张 TIFF 只建立一次 base gray 和 image statistics。Scan canvas 先按 format 与容量筛选，
再根据像素长宽比唯一匹配；不会选择“最近 profile”。Long/short px/mm 由
`ScanCanvasEvidence` 分别拥有，TIFF DPI/PPI 只作为输出 metadata。

当前片夹 catalog：

| Profile | 物理尺寸 | 适用格式与最大张数 |
|---|---:|---|
| `135_standard` | `232 × 32.22 mm` | 135 ≤ 6；half ≤ 12；XPan ≤ 3 |
| `135_narrow` | `232 × 25.4 mm` | 135 ≤ 6；half ≤ 12；XPan ≤ 3 |
| `135_dual` | `232 × 63.44 mm` | 135-dual ≤ 12 |
| `120_standard` | `226 × 60 mm` | 645 ≤ 4；66 ≤ 3；67 ≤ 3 |
| `120_wide_224_5` | `224.5 × 63.44 mm` | 645 ≤ 4；66 ≤ 3；67 ≤ 3 |
| `120_wide_223` | `223 × 63.44 mm` | 645 ≤ 4；66 ≤ 3；67 ≤ 3 |
| `120_wide_188_5` | `188.5 × 63.44 mm` | 645 ≤ 4；66 ≤ 3；67 ≤ 2 |

Separator measurement 与 positive-content measurement 相互独立。Observed band、
edge-pair、one-sided observation 和 model-only corridor 都可以参与 bounded proposal；
prior 只约束搜索，不能冒充物理观测。

每个 proposal 产生恰好 count 个 lane-local slot。Contact/overlap 的 shared interval 会
同时并入相邻安全包络；短轴默认保留完整 authoritative lane。随后按独立 scale 的 upper
endpoint 向上换算固定毫米 protection。只有这一步可以在 source/lane 边界饱和。

当前输出使用 typed identity transform。没有 named gap 时不增加 deskew，也不会因此
review。DecisionGate 后不再改变 selected count、transform 或 boxes。

## Gate、状态与原因

`CandidateGate` 固定检查十项候选事实：

```text
scan_canvas_authority
source_content_measurement
grid_search_coverage
frame_count
slot_ordinal_assignment
slot_ownership
known_content_containment
source_lane_geometry
output_protection
output_transform
```

只有 `DecisionGate` 创建 `approved_auto`、`needs_review` 和 typed reasons。常见 review
原因包括：

- `scan_canvas_authority_unavailable`
- `automatic_count_unresolved` 或 `requested_count_unfulfilled`
- `grid_search_coverage_outcome_risk`
- `slot_ordinal_assignment_unresolved`
- `slot_ownership_unbounded`
- `known_content_containment_unbounded`
- `source_lane_geometry_invalid`
- `output_protection_unavailable`
- `output_transform_unavailable`

## 输出、report 与诊断

普通自动批准会生成：

```text
x5_crop_output/
  原文件名_01.tif
  原文件名_02.tif
  ...
  _debug/
  _debug_analysis/
  needs_review/
  x5_crop_report.jsonl
  x5_crop_summary.csv
  x5_crop_run_manifest.jsonl
```

只有启用相应选项时才写 Debug 或 report：

- `--report`：写 current JSONL/CSV。
- `--debug`：写带 separator、Grid 与 crop 的轻量预览。
- `--debug-analysis`：写 source、measurement、Grid、Gate 与输出摘要。
- `--diagnostics`：只读诊断；隐含 report、Debug Analysis 与不复制 review 文件。它保留
  同一 DecisionGate 结果和 final boxes，但不写 frame TIFF。
- `--no-copy-review-files`：不复制需要 review 的原 TIFF。

Current report：

```text
schema_id       = detection_report
schema_revision = bounded_safe_crop_grid
```

Report 保存 count request/candidate range、selected count、calibration receipt ID、
observed/inferred provenance、逐 count/lane/component 工作量、dominance、slot/interaction、
safe/protected envelopes、两级 Gate、transform、final boxes 与 TIFF fidelity receipt。
Report 是审计产物，不是 detection cache。

## TIFF 保真与错误

原 TIFF 永不修改。每个 approved ROI 只从原图采样一次；写出后立即复读，并检查：

- dtype、axes、shape 与通道结构；
- Photometric、BitsPerSample、SampleFormat 与 planar configuration；
- ICC profile/色彩空间；
- resolution 与 resolution unit；
- description、datetime、software 和支持的 metadata tags；
- 像素逐值相同；
- `same` 保持源 NONE/LZW 等已知无损压缩，`none` 写无压缩 TIFF。

读取、写出、原子替换或复读失败会记录独立 `FailedInput` 与 terminal stage；不会改写已经
得到的 DecisionGate 判断，也不会生成成功 receipt。

## 验证声明边界

当前 accuracy completion 只由九张 source-SHA-bound、用户确认 geometry 的黄金样片支撑，
展开为 14 个 fixed/explicit/auto 场景。Containment 只检查 inverse-transform 后的输出
source footprint 是否完整包含确认 polygon，允许更大或重叠。

111 条 manifest 只用于非阻断 coverage audit；重复 SHA 单列，record 数不等于独立真实
样片数。当前 `real_holdout = unavailable`；XPan、120-645 等无真实样片的 coverage cell
标记 `real_sample_coverage = unavailable`，但不因此制造 review。

正式性能合同使用固定 24 张真实 TIFF、`--jobs 2`、一个空 output root 下的 `cold` 与
`measured-1/2/3` 四次运行。四次都实际写出并复读 frame TIFF，只以三次 measured 的中位数
判断 `<= 5.0 秒/张`。

## 移除与许可

删除 X5 Crop 文件夹即可移除程序和该文件夹中的输出。安装的 Python packages 可能被其它
程序共用，X5 Crop 不提供批量卸载脚本。

许可证：MIT。发布包根目录包含 `LICENSE`；GitHub 上也可查看
[完整文本](https://github.com/rrriiicccooo/X5-Crop/blob/main/LICENSE)。
