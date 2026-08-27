# 黄金基线标注器

本工具把 tracked diagnostic cohort 逐张转换为可人工审核的边界 proposal。它只服务本地黄金校准，
不属于 production detector、公开用户界面或发布包；任何机器拟合、红线导入和预览图在用户最终确认
前都不是 accuracy reference。

## 黄金验收语义

这套语义统一适用于 gold v1、v2 和以后版本：用户确认的 polygon 是**最内侧可接受的无 bleed
裁切基准**，不是对真实内容边界的 100% 测量，也不是 detector 唯一正确答案。人工审核的目标是尽量
贴近真实内容边界，并确认按该 polygon 裁切已经可以直接使用。

Accuracy 采用单向包含关系，而不是要求检测结果与红线逐像素重合：

- candidate 和正式 `required_source_footprint` 必须完整包住确认 polygon；任一边或角点向其内侧越界
  都失败。浮点 epsilon 只处理数值计算，不构成可切入的像素容差。
- 每一侧允许在对应确认 W/H span 的 5% 以内向外形成安全包络；uncertainty、residual、bleed 和命名的
  sampling allowance 都消耗这份预算。
- Runtime 的 `enclosing_support_pair` 仍遵守自己的 `1.1H` 自动决策合同；进入黄金 accuracy 时还必须
  同时满足上述逐侧单向合同，不能用总 span 掩盖单侧过度外扩。

只有带 `boundary_pair` reference 的内容 Frame 进入几何 accuracy。真正的 `blank_exposure` slot 没有
可见内容边界，其 `reference_geometry` 明确为 `not_applicable`：人工不画 `start/end`，页面不画绿色
Frame，也不要求凭空确认位置。这不是漏标或 unresolved；slot ordinal 和显式 count 仍保留，Runtime
仍按 format/count/template 输出对应空 TIFF。残缺曝光、源截断和肉眼难辨的内容格仍需要成对 reference，
不能借用 `not_applicable` 跳过审核。

## 启动

在仓库根目录运行：

```bash
python3 -m tools.manual_annotation
```

默认操作会先补齐缺失 proposal，再启动仅监听 `127.0.0.1`、带随机 token 的本地页面并打开浏览器。
首次批量准备也可单独运行：

```bash
python3 -m tools.manual_annotation prepare
python3 -m tools.manual_annotation audit
```

`prepare --sample-id S063` 只处理指定 identity；`--force-machine` 只重建未触碰的
`machine_proposal`，不会覆盖 `human_adjusted` 或 `user_confirmed`。源 TIFF 和校准工作副本始终只读。

## 审核流程

1. 在左侧按 format、状态或 sample/SHA 筛选；每次只打开一个有界预览。
2. 先检查两条共享短轴边，再检查该 source 中适用的每对长轴边。绿色四边形是这些直线交点
   围成的基础照片区域，不包含产品 bleed；空曝光 slot 没有人工长轴边或四边形。
3. 点击边界后拖整条线可沿法向移动，拖端点可修正斜率；方向键移动 1 px，按住 Shift 移动
   10 px。`[` / `]` 每次逆时针/顺时针旋转 0.01°，Shift 为 0.1°；整线绕中点旋转，选中端点时
   绕该端点旋转。`⌘Z` / `Ctrl+Z` 撤销。
4. 鼠标所在位置的右侧局部图直接读取原 TIFF 的 1:1 像素，并叠加该 source 的两条共享边和
   全部适用的成对长轴边；选中线显示为半透明黄色芯线和轻量深色轮廓，既保持选择状态，又能看清线下的
   真实像素与物理边缘。总览只负责导航，
   最终应在局部图中确认边界没有危险切入真实画面。常规窗口下，512×512 原图块使用约
   512×512 的检查区；窗口较窄时才按可用宽度收缩。不需要拖线时，点击“完整高度审阅”或按 `F`，
   首次进入会从片带长轴起点开始，横向片带即图片最左端；再次进入沿用当前审阅位置。检查区会占满
   浏览器内容区，并按当前位置两条共享边计算短轴 H，让完整 H 占可用交叉轴约 94%，
   上下保留少量余量。该模式直接从原 TIFF 读取所需源区域，再按当前屏幕尺寸缩小，不放大有界总览
   JPG。每个有内容 reference 的 Frame 由同一套共享边和成对长轴边闭合，并按 Frame ordinal 使用与
   Debug Analysis 一致的稳定多色半透明填充；`start` 为洋红色，`end` 为橙色且始终画在填充之上，
   接触 Frame 复用的 `start/end` 物理边显示为两色交替虚线。叠片中的两条独立边仍按各自角色着色，
   重叠区域会叠加加深。点击任一线可选中整线，并直接用方向键或 `[` / `]` 修改；点击空白处只沿
   胶片长轴移动，短轴始终回到共享边中间。按 `F` 或 `Esc` 恢复 1:1 标注布局。
5. 同一 source SHA 若有多个 count，页面仍只显示一个 source reference，不建立 count 页签。最大显式 count
   任务定义该 source 的物理 Frame 集；其他 count 只能按长轴顺序引用该集合的子集，不能再生成另一套黄金矩形。
   相同物理 Frame 只画一次。勾选“本 source reference 已审核”一次即覆盖该 source。底层 count 任务仍各自保存
   明确的 `slots` 与 `adjacencies`，并共用一个 source-level `boundary_pool`，不会把 count 绑定到 SHA。
   每个有内容 slot 通过 `start_boundary_id` / `end_boundary_id` 明确长轴起止边，并与
   `shared_edges` 的 `short_low` / `short_high` 共同唯一确定四边；后两者在横向片带中对应
   top/bottom，在纵向片带中对应显示坐标的 left/right。
   `contact` 的相邻照片共享同一条物理线；`overlap` 保留交叉的两条边。`slot_kind` 保留空片、残缺
   曝光和源截断；只有 `blank_exposure` 使用 `reference_geometry: not_applicable`，且不能通过少输出
   一格来隐藏。
6. source reference 审核后，点击“确认整张黄金基线”。最终弹窗只提供取消与确认；一次确认表示共享边、
   全部适用边界、原生像素和无 bleed 基础裁切安全性均已检查。确认后的 source 立即冻结，页面按队列顺序
   自动打开下一张未完成样片；全部完成时停留并提示。

机器 proposal 只减少起点工作量。遇到 contact、overlap、曲边、老化相机造成的不规则片距或边界
歧义时，按物理边界修正；无法确定的 source 不确认，保持待审。

每条线还保存 `review_basis`：肉眼直接可见、可见内容极限、按 frame width 估计、机器补线或原生像素
人工调整必须可区分。最终确认后，`human_width_estimate` 仍是可审计的安全裁切估计，但不是独立观察到
的真实边缘：黄金 accuracy 不允许该方向单独造成内切或 5% 外扩阻断；同一 Frame 其余可见边仍正常
阻断，Runtime 的源内安全与 Gate 也不改变。红线数量不足时保留机器补线并在页面提示；若拟合出的红色共享边会让任一照片
离开源栅格，只采用仍能形成源内安全矩形的红线，其余共享边保留机器 proposal 等待人工修正。

`Test/manual_review/review_context.json` 保存逐样片审阅上下文，例如空 slot、接触、叠片、猜测边、
漏光、片夹遮挡和正负片分层。它只帮助校准和审核，不能成为 production whitelist、样片特例、format
推断或 Gate authority。漏光和可舍弃小角标签用于检查通用二维 content 证据是否造成不必要的 review，
只能推动适用于全部样片的证据定义改进；标签本身不能放行某张样片。正负片只用于分别统计覆盖面和
误判，runtime 不读取该标签、不切换阈值，也不选择另一条 detector path。

## 坐标、身份与本地文件

- 权威坐标是 `raw_tiff_raster_pixel_centers`。页面按 TIFF Orientation 1–8 做可逆显示映射，保存时
  回到原始 TIFF 像素中心，不以缩略图坐标为准。
- Manifest 必须与 tracked `tools/regression/cohorts/diagnostic_unreviewed.jsonl` 在
  sample、format、count、相对路径和 source SHA 上完全一致；工具不从文件名或目录猜 count。
- 记录按 source SHA 去重。同字节、多 count 的样片只解码和标注一次物理边界。
- 本地状态保存在 `Test/manual_review/source_annotations/`：`records/` 是可恢复的原子 JSON，
  `previews/` 是有界导航 JPG，`review_artifacts/` 是确认快照，
  `confirmed_source_geometry.jsonl` 汇总所有已确认任务。汇总行的 `slots` 保留全部 count 语义，
  `frames` 只包含拥有 `boundary_pair` reference 的 ordinal。
- `Test/` 不受 Git 跟踪。确认只建立本地、source-SHA-bound 的最内侧可接受裁切基准，不会自动修改 tracked
  accuracy cohort；纳入阻断黄金仍需一次独立、显式的 cohort 审核。

## 状态与故障恢复

| 状态 | 含义 |
|---|---|
| `machine_proposal` | 独立有界像素算法生成，尚无人确认 |
| `human_adjusted` | 用户红线草稿已恢复，或页面中几何已被人工修改 |
| `user_confirmed` | source reference 已经最终确认，记录和快照冻结 |

页面每次修改都会带 revision 原子保存；并发或旧页面写入会因 revision conflict 被拒绝。保存失败时
不能切换样片，浏览器关闭前也会提示。重新运行默认命令会复用已保存状态；不要通过删除记录来修改
已确认基准。
