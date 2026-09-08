# X5 Crop V5 用户手册（开发预览）

- 范围：仓库 `main` 上尚未发布的 V5 源码
- 当前公开稳定版：v4.2.8；命令与行为不同，请使用该版本随包文档
- 适用输入：format 与曝光 slot 数已知的 Hasselblad / Imacon X5 片夹扫描

## 产品行为

X5 Crop 用已知 format 的设计尺寸先验建立该 source 的有界物理模板，而不是做通用照片边界识别。只有
当整张 source 的每个 slot 都有通过当前风险准入、可直接使用的裁切时，才写出正式 TIFF；否则整张进入
`needs_review`，不单独抢救部分 slot。

### Format 与 count

运行时必须提供 format。Count 可省略或明确指定：

- 省略 `--count`：确认使用匹配片夹的默认完整格数；
- `--count N`：确认实际有 N 个 slot；中间空曝光格也计数；
- count 必须为正数且不超过匹配片夹容量；
- `135-dual` 只有 12 格（每 lane 6 格）可自动处理，其它 count 进入 review。

默认完整格数：135=6、half=12、XPan=3、120-645=4、120-66=3；120-67 在普通片夹为 3、短片夹为 2；
135-dual 共 12。

V5 对所有 format 使用同一物理与安全合同。当前 development gold 尚无 `xpan`、`120-645`、
`135-dual` 的真实黄金样片，因此这些 format 是“Runtime 已实现、真实样片尚未验证”，不等同于已完成
准确度覆盖，也不会因此启用特殊禁用或宽松规则。

程序不会从文件名、画面、片夹容量或空白格猜 format 与真实照片数，也不会删除、合并或重排空 slot。
V5 没有 full/partial mode。

### 自动批准与人工检查

V5 先从整条片带建立粗略支撑和共同方向，再把 format/count 编译成有界 W/H 模板，只在理论 outer、
separator 与 top/bottom 附近做有界局部测量。Format 尺寸是跨相机先验，不是要求每台相机严格相同的
片门常量；可靠直接边缘可分别测量该 source 的共同 W/H，并保留原生位置。像素证据用于
对准模板和否决危险裁切，不能凭自身创造 format、count 或 placement。

缺失的单侧 start/end 只有在 source W 已由完整直接 Frame，或满秩的独立直接约束闭合，且该 Frame 的
另一侧直接可见时才可由共同 W 推断；推断不能覆盖已观察边界或删除反证。双侧都不可见的 Frame 只有在
校准 Grid 已有可靠 absolute anchor、对应 adjacency 完整检查且无反证时才可生成，并继续接受完整包络与
5% 预算检查。局部完整 Frame 的可靠 W 不因远处测量不完整或 placement 尚未获准而消失；空 Frame
也不阻止其它单边 Frame 使用共同 W。测量可用不等于允许自动输出，原反证、歧义和风险检查仍保留。
Direct W/H 分别取证。Format 画幅比例可以在经过黄金集校准、保留完整不确定性后让 W 约束
H：W/H compatibility 对所有 format 使用同一个“物理
毫米下限 + 相对比例”的计算方法，再由两轴 guard 推导各 format 的有界比例区间。它不能冒充直接
top/bottom、增加独立证据或用名义比例作零误差换算；比例校准不可用、与直接边界冲突或耗尽逐侧 5%
预算时，整张 source 保守进入 review。直接 top/bottom 始终优先保留原生位置。

同一已登记窗口会把多个高度的弱 gradient、tone 与 texture 信号联合检查。只有三个独立高度区域一致、
且唯一加强同一条直接边缘时，它才获得裁切坐标权限；未绑定或有多种解释的联合线只显示在 Debug 中，
不会生成新的 placement。

整条片带的共享 top/bottom 也会同时检查尖锐 transition 与宽缓 material 变化。宽缓边只有在两侧都具有
正确的外侧背景、共同极性、三个长轴区域连续支持、相容方向，并且完整包住固定 H 时，才能成为一对
outer support。它与尖锐边等价时保留尖锐边的原生坐标；两者不一致、只有单侧或存在多解时整张 source
保持 review，不按强弱分数选择。

Top/bottom 使用同一份整条 lane 短轴信号基线，避免局部查询窗口单独改变边缘强度的判断尺度。
实际边界仍只来自预定窗口内的完整观测；基线本身不会生成边界，也不会把原图外的缺失区域视为背景。

照片的直接 top/bottom 证据不必出现在同一条采样 trace 上。如果两侧各自由至少两个独立区域支持、
合起来覆盖每个待输出 Frame 的长轴范围，并且方向和固定 H 相容，程序可以把它们作为一对互补的直接
边界；它不会把共享支持数伪装成非零。覆盖缺失、任一侧只是模板推断，或存在多个同样合法的配对时，
整张 source 保持 `needs_review`。如果同一个 opposite 还能与一条严格更外侧的直接局部边缘闭合，程序也
不会让较内侧的完整配对自动获权；一条铺满 source 的边缘同样不能把只在局部出现的 opposite 外推为
整条片带边界。

已经满足共享支撑和纵向覆盖要求的上下边配对，不会因为其中一侧被更完整地观察到而失去直接测量结果。
只在局部出现的另一侧仍须通过原有覆盖检查；存在多个合法配对时继续保留 Review。

同一照片边缘的短片段会保留并联合检验。只有完整测量共同支持至少两个独立区域时，才可能成为已确认
的直接边界；多个照片格覆盖同一小片段不会增加证据强度。尚未获权的片段只作为边界假设保留，不改变
裁切位置，也不阻止继续检查缺失边界或占用全局边界配额。报告分别记录每条直接边界的原始区域数，
并区分完整测量数量与实际参与全局求解的边界数量。

正常片带使用一个共享 pitch；每个直接且 ordinal 唯一的 separator 可以约束自己的宽/窄间隔，后续
Frame 只累加一次该处实测差值。多个已证明的间隔变化仍以一次有界传播处理；任一间隔存在多种解释、
缺少必要 authority、尚不能从多个合法答案中可靠选择或未知必需 Frame 时保持 `needs_review`。
实测窄间隔不必达到格式的标称间隔下界。实测关系若不能独立确定全部模板参数，程序使用已有校准范围
继续检验同一位置；校准不可用或不相容时保留 Review，已确认的直接坐标不变。
拟合相容性按当前模型和当前直接锚点判断，不沿用调整前的残差结论；局部补边不改变全局残差口径。
片带端部的窄材料带可能位于照片内或照片外；内外两侧已有的边界证据都会保留，不仅凭窄带强选内侧。
原图或查询范围截断的边缘信号不能单独提供精确边界位置；尚未测量到的区域不视为已确认的背景。
照片边缘的窄材料带也不会覆盖已有的边界角色候选；系统会保留可能的解释，并用整条片带的约束核对。
存在多种边界解释时，各方案分别核对局部边界；尚不能安全确认的扫描件仍进入 Review。
同一横向边界分别核对各方案的照片区间，只有每个方案都满足原有覆盖条件时才共同使用；候选数量不增加证据强度。
多个离散位置尚未分出首选时，各份待检验范围仍受自身已确认的直接坐标联合约束；这不会解除 Review。
当前 Runtime 尚未启用可用性评分；Review 是现有选择能力的边界，不意味着产品要求证明唯一真实裁切。
报告保留每条 lane 已有的首选与单个备选裁切范围；无法生成时记录具体原因。开发黄金分析独立评价
每份范围，允许多份同时安全，并区分“不安全”和“无法评价”。每份裁切范围还记录数值预算和带单位、
来源及缺失原因的物理特征；数值预算评价与最终批准条件分开呈现。这些记录不改变自动批准条件。
离线开发排序按原图分组评估，并分开报告折外与样本内结果；分数不是安全概率，不参与实际裁切选择。
Contact 与 overlap 是 challenge，不是预定终态：标准 detector 与 Gate 判定满足直接可用准入时可以自动批准，
证据不足时安全 review 同样正确。已证明关系只在相邻的 END/START 增加 topology protection，并继续计入
同一份逐侧 5% 总预算；它不能证明 topology。V5 不为它们启用第二套 detector 或独立 bleed 预算。

选定 placement 后，程序才判断是否铺满片夹：只检查 outer 外侧能否再容纳一个 W，不回头搜索或居中。
135-dual 两条 lane 都必须满足完整性。

## 安全裁切、bleed 与 deskew

照片 aperture 的产品 bleed 为：

```text
start/end = max(0.15 mm, 0.7% W)
top/bottom = 0.25 mm
```

测量不确定性、局部 residual 与 bleed 共同消耗每侧最多 5% W/H 的安全外扩预算，边与边之间不能借用。
这是当前模型的风险预算，不是对真实边界误差的直接测量。开发黄金另以人工基线检查最终裁切的方向性
包含与实际 5% 外扩；机器不必逐条复原人工线。源截断样片比较实际确认的裁剪后多边形，
逐侧诊断与完整包含判定一致，不要求保留 TIFF 外不存在的内容。
若直接观察到一对连续 outer support 完整包住固定 H，且总高度不超过 `1.1H`，它可以替代不可用的
aperture top/bottom；这对直接支撑不依赖 W/H 比例推导。此时不再添加 0.25 mm cross bleed，但逐侧与
同一可行状态的联合对齐 padding 仍分别受 5% 预算保护；support 位置不确定性只计入逐侧预算，不会在
联合项中重复计算，也不会相加不同状态的两侧极值。唯一 support pair 已选定后，程序可用黄金集校准且
保留不确定性的 aperture-center 偏移区间收窄最坏风险；它不会把 support 冒充照片边界。Calibration
不可用时仍检查完整物理中心区间，与直接 support 冲突或完整 expansion 超过 5% 时进入 review。真实 TIFF
外缘会显式限定到实际存在的源像素，并在报告中区分是 bleed 还是联合保护触及边界；完整未限定
footprint 仍负责 5% 预算。源外缘按首末像素的单元边界表示，恒等采样完整保留首末行列；
内部照片边界不会因此外扩，黄金仍严格检查物理 polygon。双 lane 内部边界或其它 authority 越界继续进入 review，
任何限定都不会静默发生。

二维内容只在最终 post-bleed polygon 上作保守否决：bleed 内的画面可以保留；可靠内容越过最终裁切边
会阻止自动输出。尘点、别名和极小角点接触不会单独移动边界或选择另一个 placement。

通过一侧边界与共同宽度推导另一侧时，裁切范围同时保护宽度不确定性和边缘倾斜造成的角点偏移。
边界的完整位置范围保留同一组测量允许的位置变化；统计拟合的中心和窄区间不排除这些可能位置。
采样点较少但已有坐标依据的局部边界，在其它弱边界需要重新检查时仍保留，避免检测因身份回链错误中止。
已有位置区间覆盖的偏移不重复添加，完整保护仍接受原有逐侧 5% 预算检查。

Deskew 是自动批准后的可选整理，不参与检测或 Gate。`--deskew auto` 仅在两侧共同支持稳定的小角度时
旋转；证据不足、冲突或超出清理范围时保持原始方向。`--deskew off` 完全跳过观测。旋转时，图像与已
确认安全的 polygon 使用同一 affine transform，再取轴对齐包络，因此角落可能出现少量黑色 no-data，
但不能切掉已保护内容。

## 安装开发源码

请取得完整仓库 checkout；不要只复制 `X5_Crop.py`，也不要把 GitHub 自动生成的 Source code 压缩包
当作稳定发布包。普通用户应下载 [GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases)
中的 v4.2.8。

V5 开发源码支持 Python 3.12–3.14：

- macOS：`tools/install/X5_Crop_Mac_install.command`
- Windows：`tools/install/X5_Crop_win_install.bat`

未来 V5 Release 包中的相同安装器位于 `install/`，不带 `tools/` 前缀。

安装器复用合适的全局 Python 和已有依赖，只补齐缺失项；未知 ownership 会在写入前停止。不会创建
私有 `.venv`，也不要求预装 Homebrew。

## 输入合同

V5 production 输入必须满足：

- 单页 TIFF；
- unsigned 16-bit；
- RGB 三通道、contiguous planar configuration；
- `NONE`、`LZW`、`DEFLATE` / `ADOBE_DEFLATE` 或 `ZSTD` 无损压缩；
- TIFF Orientation 1–8。

域外文件成为 `runtime_error`，不会静默转换。读取时规范化 Orientation，正式输出写
`Orientation=1`。

## 运行

图形启动：

- macOS：把 TIFF 放在 `X5_Crop_Mac.command` 旁并双击；
- Windows：把 TIFF 放在 `X5_Crop_win.bat` 旁并双击。

命令行示例：

```bash
python3 X5_Crop.py /path/to/scans --format 120-66 --count 2
```

主要选项：

- `input`：一个 TIFF 或目录，默认当前目录；
- `--output PATH`：全新输出目录；
- `--format`：`135`、`135-dual`、`half`、`xpan`、`120-645`、`120-66` 或 `120-67`；
- `-n, --count N`：显式 slot 数；省略表示确认默认完整 count；
- `--layout`：`auto`、`horizontal` 或 `vertical`；
- `--deskew`：`auto`（默认）或 `off`；
- `--jobs N`：source 并发，默认 1、上限 3；
- `--debug-analysis`：写 1,800 px 宽、高度自适应的三联诊断 JPG、开发报告和摘要，不写正式 TIFF；
- `--interactive`：交互确认 format、count、deskew 与 Debug Analysis。

没有 `--overwrite`。目标目录必须不存在；Debug Analysis 与正式裁切应使用不同的新目录，正式运行始终
重新读取原 TIFF。

## 状态、输出与退出码

每个输入只有一个终态：

- `approved_auto`：写出完整的一组正式 TIFF；
- `needs_review`：不写照片，保留最小缺失事实与建议操作；
- `runtime_error`：该输入失败，其它输入继续。

Debug Analysis 显示模板、实际观察、winner/runner、画幅比例原始/保护区间及推导 H、最终 footprint、
逐边 measurement/bleed/residual 预算与首个阻断原因；共享 support 的同一状态斜率不会在 footprint 与
residual 中重复计数。页面并标明
`DESKEW APPLIED`、`ROTATION NOT NEEDED` 或 typed `DESKEW SKIPPED`。它只读取同次检测事实，不会
重新求解。

默认输出：

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

正式 TIFF 只由 `tifffile + imagecodecs` 读写，并检查位深、通道、ICC、resolution、支持的 metadata、
无损压缩和 `Orientation=1`。程序先写 staging，全部完成后一次 rename；已有目标不会被遍历、覆盖或
删除。

License: MIT — [GitHub LICENSE](https://github.com/rrriiicccooo/X5-Crop/blob/main/LICENSE)
