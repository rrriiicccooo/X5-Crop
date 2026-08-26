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
2. 先检查两条共享短轴边，再检查当前 count 页签中的每对长轴边。绿色四边形是这些直线交点围成的
   基础照片区域，不包含产品 bleed。
3. 点击边界后拖整条线可沿法向移动，拖端点可修正斜率；方向键移动 1 px，按住 Shift 移动
   10 px。`[` / `]` 每次逆时针/顺时针旋转 0.01°，Shift 为 0.1°；整线绕中点旋转，选中端点时
   绕该端点旋转。`⌘Z` / `Ctrl+Z` 撤销。
4. 鼠标所在位置的右侧局部图直接读取原 TIFF 的 1:1 像素，并叠加当前 count 任务的两条共享边和
   全部成对长轴边；选中线显示为带深色轮廓的黄色，避免在白色片基或暗部中消失。总览只负责导航，
   最终应在局部图中确认边界没有危险切入真实画面。常规窗口下，512×512 原图块使用约
   512×512 的检查区；窗口较窄时才按可用宽度收缩。
5. 同一 source SHA 若有多个 count，逐个切换页签并勾选“本任务边界已审核”。不同任务复用一个
   source-level `boundary_pool`，但各自保存明确的 `slots` 与 `adjacencies`，不会把 count 绑定到 SHA。
   `contact` 的相邻照片共享同一条物理线；`overlap` 保留交叉的两条边；空片、残缺曝光和源截断分别
   记录在 `slot_kind`，不能通过少输出一格来隐藏。
6. 所有 count 都审核后，点击“确认整张黄金基线”，逐项确认共享边、任务边界、原生像素检查和
   无 bleed 基础裁切安全性。确认后的 source 立即冻结，不可继续编辑。

机器 proposal 只减少起点工作量。遇到 contact、overlap、曲边、老化相机造成的不规则片距或边界
歧义时，按物理边界修正；无法确定的 source 不确认，保持待审。

每条线还保存 `review_basis`：肉眼直接可见、可见内容极限、按 frame width 估计、机器补线或原生像素
人工调整必须可区分。红线数量不足时保留机器补线并在页面提示；若拟合出的红色共享边会让任一照片
离开源栅格，只采用仍能形成源内安全矩形的红线，其余共享边保留机器 proposal 等待人工修正。

`Test/manual_review/review_context.json` 保存本轮逐样片审阅上下文，例如空 slot、接触、叠片、猜测边、
漏光、片夹遮挡和正负片分层。它只帮助校准和审核：不能成为 production whitelist、样片特例、format
推断或 Gate authority。正负片只作覆盖面分层；production 仍使用同一物理检测路径。

## 坐标、身份与本地文件

- 权威坐标是 `raw_tiff_raster_pixel_centers`。页面按 TIFF Orientation 1–8 做可逆显示映射，保存时
  回到原始 TIFF 像素中心，不以缩略图坐标为准。
- Manifest 必须与 tracked `tools/regression/cohorts/diagnostic_unreviewed.jsonl` 在
  sample、format、count、相对路径和 source SHA 上完全一致；工具不从文件名或目录猜 count。
- 记录按 source SHA 去重。同字节、多 count 的样片只解码和标注一次物理边界。
- 本地状态保存在 `Test/manual_review/source_annotations/`：`records/` 是可恢复的原子 JSON，
  `previews/` 是有界导航 JPG，`review_artifacts/` 是确认快照，
  `confirmed_source_geometry_v3.jsonl` 汇总所有已确认任务。
- `Test/` 不受 Git 跟踪。确认只建立本地、source-SHA-bound 的最内侧可接受裁切基准，不会自动修改 tracked
  accuracy cohort；纳入阻断黄金仍需一次独立、显式的 cohort 审核。

## 状态与故障恢复

| 状态 | 含义 |
|---|---|
| `machine_proposal` | 独立有界像素算法生成，尚无人确认 |
| `human_adjusted` | 用户红线草稿已恢复，或页面中几何已被人工修改 |
| `user_confirmed` | 全部 count 与四项检查已明确确认，记录和快照冻结 |

页面每次修改都会带 revision 原子保存；并发或旧页面写入会因 revision conflict 被拒绝。保存失败时
不能切换样片，浏览器关闭前也会提示。重新运行默认命令会复用已保存状态；不要通过删除记录来修改
已确认基准。
