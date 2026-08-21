# X5 Crop V5 用户手册（开发预览）

- 本文对象：仓库 `main` 的 V5 current-only 开发源码，尚未公开发布
- 当前公开稳定版：v4.2.8；其命令和行为不同，请使用 Release 包内随附文档
- 适用对象：用户已经知道胶片格式和照片格数的 Hasselblad / Imacon X5 片夹扫描

## 产品行为

X5 Crop 把输入看成“已知格式模板的自动对准”，而不是通用照片边界识别。用户提供 format 和
照片格数；程序使用固定物理宽高、整条片带的方向、照片组 outer、separator 和二维内容保护来
放置模板。只有整张 source 的全部 slot 都能安全输出时才写正式照片，否则整张进入
`needs_review`，不做局部挽救。

程序不从文件名、画面内容或片夹容量猜 format 或真实照片数。Count 包括中间空白曝光格；空白格
不会被删除、合并或改变顺序。

### Format 与 count

命令行只有 format 和可选 count，没有 full/partial 模式：

- 省略 `--count`：用户确认使用匹配片夹的默认完整格数；
- 明确 `--count N`：用户确认实际有 N 个 slot；
- 明确 count 必须为正整数，并且不能超过匹配片夹的容量；
- `135-dual` 的默认值是 12，每 lane 6；明确输入其它值会进入
  `needs_review`，程序不猜两条 lane 的分配。

完整格数为：135=6、half=12、XPan=3、120-645=4、120-66=3；120-67 普通片夹为 3、短片夹
为 2。135-dual 总计 12。

程序在 placement 已经选定后才判断照片组是否铺满片夹：只检查真实 outer 外侧是否还能放下一个
format 宽度 W，不附加 gap。这个事实不用于搜索，也不提供长轴居中权限。单 lane 不要求居中；
135-dual 只有两条 lane 都确认铺满时才允许自动输出。

## 检测主线

### 从整体到局部

V5 继承 v4.2.8 最有效的行为，但不复制旧实现：

1. 先从片夹、胶片材料边或长距离稳定结构得到粗位置和共同方向；
2. 按 format、count 和尺度放下固定 W/H 模板；
3. 先识别 separator material band 和 outer 所在的有限区域；
4. 只在理论边界附近做一次有界局部精测；
5. 用实际观察相对理论模板的偏差解释整体平移、pitch 微调或一次局部位移；
6. 位置唯一且安全事实齐全后立即停止，不继续寻找更多候选。

粗支撑只回答“片带大概在哪里、朝哪个方向”，不能单独宣布照片边界。局部观察在绑定模板以前也
没有第几格、start/end 或 top/bottom 身份。同一个 separator 的两条边、band 和多条 trace 仍只算
一个物理结构，不会重复投票。

First/last 看不清时并不必然失败。只要内部 separator 或其它独立观察已经确定 phase、pitch 和
ordinal，模板可以推导缺失端点。没有任何直接 phase anchor 时，模板不能自己证明自己。

### 固定尺寸、separator 与局部异常

同一片条的全部照片共享 format W/H、扫描尺度和 deskew 方向。每格不会因像素噪声改变尺寸；
间隙只改变位置。

正常片条使用共同 pitch。某一 adjacency 有直接证据表明宽缝或窄缝时，程序最多允许一次局部
advance：异常点以后的照片整体移动一次，后续仍恢复共同 pitch。异常位置不明确、需要两次以上
位移、接触或 overlap 时保持 `needs_review`。当前没有用户确认的 overlap 黄金，因此 V5 不自动
批准叠片，也不启用特殊 overlap bleed。

### Deskew 与轻微弯曲

Deskew 同时参与检测和输出。程序用整条片带共享的直线方向计算理论边界，避免斜片条在首尾产生
明显位置误差；正式输出再从原始 16-bit TIFF 按同一几何采样。

轻微弯曲不建立曲线模型。只有已经证明角色正确、由直接像素连续覆盖整条片带，并且在剔除有界
异常点后每条保留 trace 都一致证明同一内外关系的边界，才能保留其局部位置；它不能改写整条片带
的共同方向，也不能在已有足够直线边界时重标定全局模板。弯曲残差只进入胜出 placement 的安全
范围。若所需保护超出预算，整张 source 进入人工检查。每张照片不会拥有独立旋转或自由四边形。

## Top/bottom 与可接受 outer

程序不需要区分一条外侧支撑究竟是片夹边还是胶片材料边，但会区分两种最终用途：

### 照片 aperture

有资格代表照片真实 top/bottom 的局部观察必须同时满足有限位置、共同方向、正确内外关系和固定
H 闭环。可以使用：

- 直接 top 与 bottom；
- 一条 source-wide 的直接边，加固定 H 推导另一侧；
- 一个有明确 role authority 的直接边，只要在 selected frame domains（数量至少为 3）中
  逐一有 direct trace，即使独立支持记录为 2 个区域，也可作为固定 H 的单侧 anchor；
- 同侧多个相距较远、能够证明属于同一直线的 fragment。

短小照片内部黑线、只因坐标接近而拼接的 fragment、两个不同合法位置都不能决定 outer。存在两个
不同答案时不会平均或按梯度强弱硬选。上述单侧例外仍要求完整方向和同一个 binding 在每个
selected domain 中分别有 direct trace；selected domain 少于 3 个、缺少一个 domain、两个不连通
fragment 合计覆盖、role 未授权或方向不完整时，程序继续人工检查。片夹短轴中心只作兼容事实，
不是该 authority 的必要条件；另一侧仍只由固定 H 推导，局部 departure 继续进入输出预算。

### 包住照片的外侧支撑

如果找不到可靠 aperture，但存在一对直接、连续且共同方向的外侧支撑，它们完整包住固定 H，且
总高度不超过 `1.1 × H`，程序可以直接把这对支撑作为输出 top/bottom。这允许使用片夹边或胶片
材料边裁切，并保留少量可接受黑边。

这里的总高度只取自这对直接支撑的最坏实测跨度。程序不会把同一 placement 不同可行状态中的
top 与 bottom 极值拼在一起，制造一个并不存在的更高支撑跨度。

两侧必须来自同一种用途：不能一侧按 aperture、另一侧按外侧支撑。两侧直接闭环且唯一的
aperture 优先；如果 aperture 只有单侧直接观察、另一侧依赖固定 H 推导，或者 aperture 存在多个
不同答案，一对唯一且直接证明的外侧支撑可以成为更强的输出边界。外侧支撑不是放宽后的猜测，
而是另一种有直接连续性证明的完整输出边界。

## Bleed、联合安全范围与 5% 预算

Bleed 是固定的产品边距，不是测量置信度，也不参与选择 placement。

使用照片 aperture 时：

```text
start/end bleed = max(0.15 mm, 0.7% W)
top/bottom bleed = 0.25 mm
```

程序先保留同一个胜出 placement 的所有联合可行状态，包括 phase、pitch、direction、cross、
一次局部位移和直线残差，再加入 bleed。它不会把互相不能同时发生的各项最大误差简单相加，也
不会合并 runner-up。

使用 aperture 的自动输出上限是四边各自最多扩张 format 对应尺寸的 5%。这 5% 包含测量不确定性、
直线残差和 bleed；四边不能互借额度。以 36 mm 宽的 135 为例，正常 start/end bleed 是
0.252 mm，占单边 1.8 mm 上限的 14%；0.25 mm 的 cross bleed 占 24 mm 单边 1.2 mm 上限的约
20.8%。

使用外侧支撑时，top/bottom 不再加 0.25 mm bleed，也不套用 aperture 的单边 5%：它使用
“直接支撑总高度不超过 1.1H”这个独立合同。Start/end 仍使用正常 bleed 和单边 5%。

最终所需 footprint 不会被静默裁到 source 或 lane 范围内。只要超出可采样范围，或者任一边超过
对应预算，整张 source 就进入 `needs_review`。

二维内容只回答“当前输出会不会明显切进真实照片内容”。它不能移动边界、平分照片、创造
placement 或替某个候选加分。角落极小擦边、锯齿和尘点保持中性；连续跨过完整边界的不安全内容
才会否决自动输出。

## 安装开发源码

取得完整仓库 checkout；不要只复制 `X5_Crop.py`，也不要把 GitHub 自动生成的 Source code
压缩包当成稳定发布包。普通用户应从
[GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases) 下载 v4.2.8，并阅读包内文档。

V5 开发源码支持 Python 3.12–3.14，并固定所需模块版本。在仓库根目录运行：

- macOS：`install/X5_Crop_Mac_install.command`
- Windows：`install/X5_Crop_win_install.bat`

安装器复用合格的全局 Python 和现有依赖，只安装缺失项。来源无法安全确认时会在改动前停止。
Homebrew 不是前置条件，也不会建立私有 `.venv`。卸载器只删除收据证明由 X5 Crop 新增且未被
其它包使用的依赖。

## 输入合同

V5 正式输入域为：

- 单页 TIFF；
- unsigned 16-bit；
- RGB、三通道、contiguous planar configuration；
- `NONE`、`LZW`、`DEFLATE` / `ADOBE_DEFLATE` 或 `ZSTD` 无损压缩；
- TIFF Orientation 1–8。

不满足冻结域的文件会记录为 `runtime_error`，不会静默转换。Orientation 在读取时规范化，输出
写为 `Orientation=1`。

## 运行

图形化启动：

- macOS：将 TIFF 放到启动器目录，双击 `X5_Crop_Mac.command`；
- Windows：将 TIFF 放到启动器目录，双击 `X5_Crop_win.bat`。

命令行示例：

```bash
python3 X5_Crop.py /path/to/scans --format 120-66 --count 2
```

主要参数：

- `input`：一个 TIFF 或包含 TIFF 的目录；省略时为当前目录；
- `--output PATH`：全新输出目录；
- `--format`：`135`、`135-dual`、`half`、`xpan`、`120-645`、`120-66` 或 `120-67`；
- `-n, --count N`：可选的正整数 slot 数；省略表示确认匹配片夹默认值；
- `--layout`：`auto`、`horizontal` 或 `vertical`；
- `--jobs N`：source 并发数，默认 1，上限 3；
- `--debug-analysis`：只写 1800 px 宽、自适应高度的三联诊断 JPG、development report 和
  summary，不写正式 TIFF 或 review copy；
- `--interactive`：交互选择 format、count 和 Debug Analysis。

交互模式对每个 format 都显示 count。直接回车表示确认匹配片夹的默认完整格数；输入其它合法
数字表示用户明确确认该 count。`135-dual` 的交互相同，但除 12 外都会进入人工检查。

没有 `--overwrite`。输出目录必须尚不存在，程序不接管或删除旧输出。Debug Analysis 与正式
裁切应使用不同的新目录；正式运行始终重新读取原 TIFF。

## 状态、输出与退出码

每个输入只有一个终态：

- `approved_auto`：写出完整的一组正式 TIFF；
- `needs_review`：不写照片，只保留原扫描件、最小缺失事实和建议操作供检查；
- `runtime_error`：该输入失败，其它输入继续。

Debug Analysis 展示理论模板、实际观察、偏差形状、直接与推导边界、winner/runner 差异、最终
输出 footprint、预算使用和第一个阻止自动输出的原因。失败会区分用户可修正输入、重新测量可
恢复和系统不应自动猜测三类。Debug 只读取同一次检测事实，不重新求解。

默认结构：

```text
x5_crop_output/
  原文件名_01.tif
  原文件名_02.tif
  needs_review/
  _debug_analysis/
  x5_crop_report.jsonl
  x5_crop_summary.csv
```

退出码：

- `0`：成功发布且没有 `runtime_error`；
- `1`：已发布但含 `runtime_error`，或全部输入失败；
- `2`：命令行、输入集合或运行前检查失败；
- `3`：全新输出目录无法安全发布。

正式 TIFF 只由 `tifffile + imagecodecs` 读写，并保真检查位深、通道、ICC、resolution、受支持
metadata、无损压缩与 `Orientation=1`。程序先写 staging，全部完成后一次 rename 发布；已有目标
不会被遍历、覆盖或删除。

License: MIT — [LICENSE](../LICENSE)
