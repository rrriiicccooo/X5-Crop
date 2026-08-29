# 黄金基线标注器

本地标注器把 tracked diagnostic cohort 转为可人工审核的 source-SHA-bound 几何。它不属于 production
detector、公开界面或发布包；机器 proposal、红线导入、像素精修、预览和确认图都不会自动成为黄金。

## 黄金权限与验收

用户确认的是**最内侧可接受的无 bleed 裁切基准**：它尽量贴近真实内容边界，并保证按该 polygon 裁切
可以直接使用；它不是内容边界的绝对测量，也不是 detector 唯一正确答案。

Accuracy 采用方向性包含合同：

- candidate 与正式 `required_source_footprint` 必须完整包住确认 polygon；任何边或角点向内越界都失败。
- 每侧最多向外使用对应确认 W/H span 的 5%；uncertainty、residual、bleed 与命名的 sampling allowance
  共用这份预算，不能跨边借用。
- `enclosing_support_pair` 仍须满足 runtime 的 `1.1H` 合同，同时满足黄金逐侧包含与外扩限制。

只有带 `boundary_pair` 的内容 Frame 进入几何 accuracy。`blank_exposure` 没有可见内容边界，必须使用
`reference_geometry: not_applicable`：人工不画线、不确认虚构位置，但 slot ordinal 与显式 count 仍保留，
runtime 仍输出对应空 TIFF。残缺曝光、肉眼难辨和源截断 Frame 仍需成对边界。

`source_truncated` 只用于 TIFF 确实截断物理 Frame 的情况。记录保留可能越出 TIFF 的物理直线，审核与
accuracy polygon 使用“物理 Frame 与 TIFF 栅格的交集”，并沿 TIFF 外缘闭合。普通、残缺曝光和未知
Frame 必须完整位于源内；只有类型标签、没有实际越界几何的记录不能确认。该规则对四条外缘和
Orientation 1–8 一致，不建立样片特例。

活动数据只有 `Test/manual_review/gold_calibration/<format>/` 这一套校准池；不区分 v1/v2，也不建立
archive。一个 source SHA 只有一套物理几何，同源多 count 分别保留 task mapping。只有当前
`user_confirmed` 记录具备黄金权限；确认集合为空时，accuracy 必须报告
`calibration is incomplete`，不能回退旧 cohort。

## 启动与文件

在仓库根目录运行：

```bash
python3 -m tools.manual_annotation
```

默认命令补齐缺失 proposal，再启动只监听 `127.0.0.1`、带随机 token 的页面并打开浏览器。辅助命令：

```bash
python3 -m tools.manual_annotation prepare
python3 -m tools.manual_annotation audit
```

`prepare --sample-id S063` 只处理指定 identity；`--force-machine` 只重建未触碰的
`machine_proposal`，不会覆盖人工工作。源 TIFF 与工作副本始终只读。

本地状态位于 `Test/manual_review/source_annotations/`：

- `records/`：原子 source record；
- `previews/`：有界导航 JPG；
- `review_artifacts/`：确认时生成的审阅快照；
- `confirmed_source_geometry.jsonl`：全部当前确认 task 的派生汇总。

权威坐标为 `raw_tiff_raster_pixel_centers`。页面只用 Orientation 1–8 的可逆映射显示，保存时回到原始
TIFF 像素中心。Manifest 必须与 tracked diagnostic cohort 的 sample、format、count、相对路径和 source
SHA 完全一致；工具不从路径猜 count。`Test/` 不受 Git 跟踪，确认不会自动改写 tracked accuracy cohort。

## 边界、Frame 与评测角色

每条活动线必须有一种 `review_basis`：

- `unclassified`：依据尚未确认，阻止 source 审核与最终确认。
- `directly_visible`：人类能从原 TIFF 的可靠亮度或颜色分界确信真实内容边缘。证据可以很淡、很短，
  不要求覆盖完整 H，也不要求 detector 检出同一线；验收只看最终裁切是否满足黄金合同。
- `visible_content_limit`：仍可见内容的极限。裁切进入线内会阻断；相对该线向外不受 5% 阻断。
- `human_width_estimate`：由同源直接可见 Frame 的一致宽度推算。该侧线内线外都不阻断 accuracy。

`origin` 只记录坐标来自机器、红线、精修还是人工移动，与 `review_basis` 独立。移动坐标不得发明可见
证据；精修或人工编辑也不得清除已经声明的依据。

Frame 的 `slot_kind` 为 `image`、`partial_exposure`、`source_truncated`、`unknown` 或结构性
`blank_exposure`。同一物理 Frame 被多个 count 引用时必须共享状态。相邻关系由几何自动派生：共用一条
end/start 物理线为 `contact`；前一 end 越过后一 start 为 `overlap`；空 slot 邻接为
`not_applicable`；其余为 `separator`。页面只显示这些事实，不提供手工关系选择框。

`nominal` / `challenge` 也只从确认前的人工证据、Frame 语义、相邻关系和固定模板合同自动派生：

- contact 或 overlap 始终为 challenge；
- 非空 Frame 两侧均非直接可见，且另一 Frame 还有不同的非直接可见边界时为 challenge；
- `count <= 3` 时，2 条及以上非直接可见边界为 challenge；`count > 3` 时，4 条及以上为 challenge；
- 必需依据缺失、没有直接可见的长轴 anchor、未知 Frame、源截断几何未成立或 count 超出固定模板合同
  时为 challenge。

长轴边按唯一物理 line ID 计数，contact 共用线不重复，空曝光不参与。角色与原因在确认基线中冻结，
accuracy 会从冻结证据重新推导并核对。Nominal 必须安全自动批准；challenge 允许安全
`needs_review`，不能通过手工改类、白名单或放宽 Gate 提高通过率。

## 有界精修

所有活动线完成分类后，可以先只读评估，再写回精修 proposal：

```bash
python3 -m tools.manual_annotation refine --dry-run
python3 -m tools.manual_annotation refine
```

`--sample-id S030` 限定一个 source。工具只读取当前人工线附近的原 TIFF 窄带，不读取预览、不把完整
长图发送给模型，也不修改 TIFF：

- `directly_visible` 与 `visible_content_limit` 仅在存在唯一、稳定局部边缘时微调；歧义、证据不足、
  搜索触边或当前线已在同一模糊带时保持原位。
- `human_width_estimate` 不把局部像素冒充可见证据。至少两个同源、两侧均直接可见的 Frame 形成稳健
  宽度共识后，才从可靠对边反推，或围绕现有中心对称调整；依据仍完全不阻断。
- 任何会改变 contact/overlap、Frame 顺序、源截断交集或 schema 的移动都被拒绝。

`diagnostics.refinement` 保存逐线输入、输出、位移、证据强度和保留原因。精修不改变 `review_basis`，
不勾选 source review，也不授予黄金权限。人工随后修改坐标、依据或 Frame 状态会把相应证据标为
`adjusted_after_refinement`；有人工修改的记录不会被后续批量精修覆盖。

## 审核流程

1. 按 format、状态、边界依据、Frame 状态或评测角色筛选；每次只打开一个 source 的有界预览。同源
   多 count 不建立页签，只显示一套 source reference，并列出各 task 的映射与角色。
2. 先检查两条共享短轴边，再检查每个内容 Frame 的 start/end。总览用多色半透明区域区分 Frame；
   `start` 与 `end` 使用不同颜色，contact 共用线以双色虚线显示，overlap 保留两条独立线。
3. 点击或拖动只编辑整线。方向键沿法向移动 1 px，Shift 为 10 px；`[` / `]` 绕中点旋转 0.01°，
   Shift 为 0.1°；`⌘Z` / `Ctrl+Z` 撤销。批量分类只改变所选线的 `review_basis`。
4. 1:1 局部图直接读取原 TIFF，并以半透明选中线保留线下像素。完整高度审阅从片带长轴起点进入，
   让完整共享短轴 H 落在屏幕内；该视图显示线与 Frame 轮廓，不填充画面。`F` 或 `Esc` 退出。
5. 普通 Frame 不能被拖出 TIFF；`source_truncated` 可按物理事实外推，但必须保留有效源内交集。页面
   实时显示派生 Frame polygon 与相邻关系，防止 start/end 混淆。
6. 全部线分类并在原生像素下确认安全后，勾选 source reference 已审核，再选择“确认整张黄金基线”。
   弹窗只有取消与确认；确认后记录立即冻结，并自动打开下一张待完成 source。

机器 proposal 提示只帮助定位，不是阻断项；确认时会从冻结记录中清除。无法可靠判断的 source 不确认，
保持待审。

## Review context 与恢复

`Test/manual_review/review_context.json` 保存用户提供的空 slot、接触、叠片、估计边、漏光、片夹遮挡和
正负片等审核上下文。它只服务校准分层与预填，不是 production whitelist、format 推断、Gate authority
或另一条 detector path。漏光与可舍弃小角只能推动通用证据改进；正负片只用于覆盖统计。

对未确认记录更新 context 后，可显式同步非结构性依据与 Frame 类型：

```bash
python3 -m tools.manual_annotation reconcile-context --sample-id S030
```

已确认记录不可由该命令或页面改写。若发现冻结基线有误，应先停止使用该记录，并通过独立、受审计的
校准重置重新进入待审；当前工具不提供隐式解冻或“修补确认”的入口。

| 状态 | 含义 |
|---|---|
| `machine_proposal` | 独立有界算法生成，尚无人调整 |
| `human_adjusted` | 保留的待确认草稿或页面中已修改的几何 |
| `user_confirmed` | source reference 已明确确认，记录与快照冻结 |

每次修改都带 revision 原子保存；并发或旧页面写入会因 revision conflict 被拒绝。保存失败时不能切换
样片，关闭浏览器前也会提示。重启默认命令会复用已保存状态；不要靠删除记录修改已确认基准。
