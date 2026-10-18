# X5 Crop V5 用户手册（开发预览）

- 范围：仓库 `main` 上尚未发布的 V5 源码
- 当前公开稳定版：v4.2.8；命令与行为不同，请使用该版本随包文档
- 适用输入：format 与曝光 slot 数已知的 Hasselblad / Imacon X5 片夹扫描

## 产品行为

X5 Crop 用已知 format 的设计尺寸先验建立每张 source 的有界物理模板，而不是做通用照片边界识别。只有
当整张 source 的每个 slot 都有通过当前安全规则、可直接使用的裁切时，才写出正式 TIFF；否则整张进入
`needs_review`，不单独抢救部分 slot。

裁切保护输入 TIFF 中已经可见的照片内容。被片夹遮住、没有记录进 TIFF 的画面不属于恢复范围；可见画面及
其倾斜角点必须完整保留。

### Format 与 count

运行时必须提供 format。Count 可省略或明确指定：

- 省略 `--count`：确认使用匹配片夹的默认完整格数；
- `--count N`：确认实际有 N 个 slot；中间空曝光格也计数；
- count 必须为正数且不超过匹配片夹容量；
- `135-dual` 只有 12 格（每 lane 6 格）可自动处理，其它 count 进入 review。

默认完整格数：135=6、half=12、XPan=3、120-645=4、120-66=3；120-67 在普通片夹为 3、短片夹为 2；
135-dual 共 12。

V5 对所有 format 使用同一物理与安全合同。当前 development gold 尚无 `xpan`、`120-645`、`135-dual` 的
真实黄金样片，因此这些 format 是 Runtime 已实现但尚无真实样片准确度覆盖；不会因此启用特殊禁用或宽松规则。

程序不会从文件名、画面、片夹容量或空白格猜 format 与真实照片数，也不会删除、合并或重排空 slot。V5
没有 full/partial mode。

### 自动批准与人工检查

程序根据 format/count 建立共同 W/H 的物理模板，再用整条片带和局部边缘证据确定位置。直接观察到的照片
边界保留原生坐标；缺失边界只能由已确认的共同尺寸、位置锚点和经过检查的相邻关系推导。格式比例或外侧
支撑可以参与定位，但不能冒充直接照片边界或覆盖反证。
共同宽度的允许区间收窄时，推导边界同步使用更新后的范围；位置歧义和竞争解释仍须通过全部安全检查。
位置锚点、共同宽度和格间距的允许变化一起核算，保留直接边界的完整测量范围。不同的合法接触或重叠
解释仍需人工检查；更多局部支持本身不能排除另一种解释。存在位置或接触关系歧义时，程序分别保留
两种解释的原生边界和允许位置范围，供人工检查。
报告分别保留直接边界方案、校准模板方案以及被证据阻断的诊断方案，并显示各自的几何依据和未闭合原因。
诊断方案中的反证继续保留，仍须人工检查。
首选及保留的竞争解释分别核验自己的边界与相邻照片关系，报告显示已登记伙伴的关联证据和物理矛盾。
竞争解释尚未完整覆盖时继续人工检查；两份方案能放入同一窗口，仍不足以取得自动输出资格。

验收针对最终裁切结果：逐格对应正确、不遗漏或重复、完整保护已确认画面，并满足固定尺寸、源域和风险预算。
内部边界名称不必与人工标注一致；接触照片的同一物理边界可以同时作为上一格的结束和下一格的开始，
并用于共同模板定位；它仍是一份物理观察。
每格仍须有足够的位置与保护证据。内容遗漏、源内越界、必要依据缺失，或仍有无法完整核验和保护的竞争解释，
都会使整张 source 进入 `needs_review`。评分不能替代这些条件，也不能扩大固定框。
程序会核验已识别的完整分隔材料；某方案遗漏材料另一侧，并因此要求照片超过该格式的物理宽度上限时，
该解释会被拒绝。其它方案仍须独立通过全部安全检查。

照片归属已确定而上下边存在多个完整解释时，程序可以用同一个固定框保护全部解释；只有所有解释都通过内容
包含及整张安全检查，才可自动批准。接触或重叠照片同样使用这些检查，证据不足时保留人工检查。

分隔材料按每条扫描线上的实际坐标核查相邻关系；扫描线上存在中间边界时，该处材料不为外侧边界配对提供
支持。程序分别核查局部分隔与贯穿整张源图的分隔关系，证据不足的关系保留人工检查。

Debug Analysis 展示首选、备选和保留提案及其证据、覆盖结果与阻断原因，供人工检查。报告为每个展示的解释
保留原始证据和失败原因；显示某个解释不代表它已获裁切或自动输出权限。当前 Runtime 尚未使用开发排序
分数作裁切选择。

选定 placement 后，程序才判断是否铺满片夹：只检查 outer 外侧能否再容纳一个 W，不回头搜索或居中。
135-dual 两条 lane 都必须满足完整性。

## 固定原图坐标窗口、内容保护与 deskew

每条源 TIFF 使用共同 W/H。每个 Frame 的请求窗口固定为：

```text
source-space window = 1.1W × 1.1H
per-side margin = 5%
```

固定框只允许由脚本选择位置，不能因测量、残差、方向或评分调整窗口尺寸。它必须完整包含 TIFF 中可见的照片
内容，包括倾斜角点；可信证据要求的完整物理包络若无法放入固定框，整张 source 进入 `needs_review`。只要
可见照片内容仍受完整保护，框内定位偏移不单独构成拒绝原因。

独立证据唯一确定照片上下边时，程序使用这些坐标选择固定框位置，不把实测高度改成框内推定高度。连续
outer support 只有在可信的完整物理包络能够放入固定框时才可作为位置证据；只观察到局部支撑不能外推整段
外框，校准也不能把 support 冒充照片边界。缺少、冲突或未闭合的证据仍进入 Review。

真实 TIFF 外缘可以 source-clip，并在报告中明确记录；源边缘裁剪只针对实际存在的源像素，不会扩大或缩小
内部照片边界。内部 lane 或其它 authority 越界继续进入 review，不能通过缩小窗口绕过。固定框不能通过并集
扩大。

二维内容只在最终固定框上作保守否决：可靠内容越过固定框边界会阻止自动输出，框内偏移不单独改变位置。
通过一侧边界与共同宽度推导另一侧时，完整允许的位置范围用于选择固定框位置，不能因此调小窗口或绕过
内容保护。已有坐标依据的局部边界在弱边界重新评估时仍可保留。

Deskew 是自动批准后的可选整理，不参与检测或 Gate。`--deskew auto` 仅在两侧共同支持稳定的小角度时
旋转；证据不足、冲突或超出清理范围时保持原始方向。`--deskew off` 完全跳过观测。旋转时，图像与已确认
安全的 polygon 使用同一 affine transform，再取轴对齐包络，因此角落可能出现少量黑色 no-data，但不能切掉
已保护内容。Deskew 的轴对齐包络、真实 TIFF 边缘 clipping 和整数取整都可能改变最终输出的像素宽高；固定
尺寸指原图坐标窗口。

## 安装开发源码

请取得完整仓库 checkout；不要只复制 `X5_Crop.py`，也不要把 GitHub 自动生成的 Source code 压缩包当作稳定
发布包。普通用户应下载 [GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases) 中的 v4.2.8。

V5 开发源码支持 Python 3.12–3.14：

- macOS：`tools/install/X5_Crop_Mac_install.command`
- Windows：`tools/install/X5_Crop_win_install.bat`

未来 V5 Release 包中的相同安装器位于 `install/`，不带 `tools/` 前缀。

安装器寻找 64-bit Python 3.12–3.14，复用符合版本要求的依赖，并通过已识别的包管理器补齐或更新其余依赖。
来源不明时会在修改前停止。Homebrew 不是前置条件，也不会建立私有虚拟环境。

## 输入合同

V5 production 输入必须满足：

- 单页 TIFF；
- unsigned 16-bit；
- RGB 三通道、contiguous planar configuration；
- `NONE`、`LZW`、`DEFLATE` / `ADOBE_DEFLATE` 或 `ZSTD` 无损压缩；
- TIFF Orientation 1–8。

域外文件成为 `runtime_error`，不会静默转换。读取时规范化 Orientation，正式输出写 `Orientation=1`。

## 运行

在仓库根目录运行命令，输入可以是一个 TIFF 或扫描目录。交互模式使用
`python3 X5_Crop.py --interactive`，处理当前目录中的 TIFF。未来 V5 Release 包提供 macOS 和 Windows 双击
启动器。

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

没有 `--overwrite`。目标目录必须不存在；Debug Analysis 与正式裁切应使用不同的新目录，正式运行始终重新
读取原 TIFF。运行期间若其他操作创建了同名目标，程序会保留它并报告输出错误；请选择新的目录重试。文件
系统无法保证原子不覆盖时也会停止发布。macOS 上请将输出写入支持原子不覆盖操作的 APFS/HFS+ 卷；如需
存放到 exFAT，完成后复制整个输出目录。

## 状态、输出与退出码

每个输入只有一个终态：

- `approved_auto`：写出完整的一组正式 TIFF；
- `needs_review`：不写照片，保留最小缺失事实与建议操作；
- `runtime_error`：该输入失败，其它输入继续。

Debug Analysis 显示模板、实际观察、winner/runner、画幅比例原始/保护区间及推导 H、固定原图坐标窗口的
尺寸与位置、内容保护证据和首个阻断原因。页面并标明 `DESKEW APPLIED`、`ROTATION NOT NEEDED` 或 typed
`DESKEW SKIPPED`。它只读取同次检测事实，不会重新求解。开发报告另记录外侧区域的颜色连续性、弱信号和
测量可用状态；测量可用不代表已经识别为片夹，也不单独授权裁切。

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

正式 TIFF 只由 `tifffile + imagecodecs` 读写，并检查位深、通道、ICC、resolution、支持的 metadata、无损
压缩和 `Orientation=1`。程序先写 staging，全部完成后一次 rename；已有目标不会被遍历、覆盖或删除。

License: MIT — [GitHub LICENSE](https://github.com/rrriiicccooo/X5-Crop/blob/main/LICENSE)
