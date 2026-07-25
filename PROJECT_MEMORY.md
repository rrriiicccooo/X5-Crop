# 项目记忆

更新：2026-07-26

这是 X5 Crop 唯一跨会话检查点，只保存当前目标、已验证状态、验证边界、开放风险和精确
下一步。Git、源码、原始 TIFF、current report、Debug Analysis 与现场命令始终优先。

## 当前目标

使用已经完成的用户确认黄金基线，量化并校准 V4.9 detector：

```text
共享照片长边
→ deskew 与共享短轴
→ 成对长轴分隔边缘
→ 保守包含的安全矩形
→ 仅输出阶段应用 bleed
```

- 目标是在黄金集校准的方向性容差内形成足够准确的安全裁切，不追求数学 `0 px`。
- 保留 typed evidence、唯一 affine 坐标映射、uncertainty、`CandidateGate`、
  `DecisionGate` 与 typed unresolved。
- Bleed 只在基础几何之后扩张，不能掩盖错误几何。
- 不恢复退役审阅机制、历史 schema、alias、shim、兼容 fallback 或 runtime 白名单。

## 已验证检查点

- 分支：`main`。
- 当前 runtime：`X5_Crop.py` V4.9。
- 报告 revision：`cross_region_photo_edge_geometry`。
- 稳定发布：`v4.2.8`。
- 本地有 111 张未修改源 TIFF：47 张 `135/full`、14 张 `135/partial`、32 张
  `66/partial`、3 张 `67/full`、10 张 `half/full`、5 张 `half/partial`。
- `manifest.jsonl` 绑定同样的 111 个 source identity，并标出 9 张黄金样片。
- 人工证据链完整：9 张标注 TIFF、9 张原生分辨率复核 JPG、9 条
  `x5crop_red_markup_fit_proposal_v1`、9 条
  `x5crop_user_confirmed_golden_baseline_v1`。
- `S027=6`、`S035=6`、`S051=3`、`S055=4`、`S062=3`、`S091=3`、`S094=3`、
  `S098=12`、`S109=7`。
- `S027`、`S035`、`S051`、`S055`、`S062`、`S091`、`S094`、`S109` 属于
  `nominal_calibration`。
- `S098` 因老化相机造成非矩形与不稳定片距，属于 `irregular_geometry_stress`，不参与
  正常容差估计；runtime 不得强迫其 divider 垂直、等片距或自动 PASS。
- `red_markup_converter.py verify` 已检查 source/marked/JPG hash、线数、顺序、界内正面积
  polygon、原生 JPG 尺寸、拟合残差、proposal snapshot 与全部 confirmed row。
- Converter revision `preview_red_delta_robust_line_fit_v2` 会拒绝与强红线数量冲突的声明
  帧数，不能静默丢弃用户笔迹。

## 当前人工审阅合同

- 未修改原 TIFF 拥有 raster coordinate 与 source SHA；标注副本只保存用户直接笔迹。
- Proposal 始终保持 `pending_explicit_user_confirmation` observation，即使另有 confirmed
  row，也不会提升自身权限。
- 只有用户明确确认确切 review JPG，才能创建 baseline authority。
- 每条 confirmed row 绑定 source SHA、marked-copy SHA、不可变 proposal snapshot SHA、
  review JPG SHA、连续 source-pixel geometry 与确认后的 integer polygon。
- 模型视觉、OpenCV、SciPy、生成 JPG、hash、residual 或算法一致不能独立创建真值；
  歧义 geometry 保持 unresolved。
- `nominal_calibration` 用于估计方向、containment、content loss 与 pitch tolerance；
  `irregular_geometry_stress` 不参与阈值统计。

## 文档与工作区

- 根 `README.md` 只是精简双语 GitHub 入口。
- `docs/` 中的中文与英文用户手册、快速启动分别面向 GitHub 和 Release。
- `AGENTS.md`、`ARCHITECTURE.md`、`CHANGELOG.md` 与本文件只写中文正文。
- 受跟踪 current owner 是根文档/launcher、`docs/`、`install/`、`x5crop/` 与 `tools/`。
  历史版本只由 Git history 与 tags 保存，不维护 `archive/`。
- `Test/` 是 ignored 本地证据，不是 tracked source contract。原 TIFF、九张标注副本、
  确认 JPG、proposal、baseline、manifest、converter 与两份本地中文说明必须保留；
  cache、`.DS_Store`、临时文件和 generated output 不保留。
- `LICENSE` 保留在 GitHub，本地 sparse checkout 不保存。

## 验证边界与开放风险

- 九条确认记录建立项目实用的 safe no-bleed reference，不是独立物理测量的数学 oracle。
- Production detector 尚未对完整黄金基线进行方向性误差量化或阈值校准；`tools/verify`
  通过不能证明 named-TIFF geometry 准确。
- 比较必须经过唯一坐标映射，并分别保留 unsafe outward crossing、inward content loss、
  signed normal distance、angle 与 containment，不能压缩为无方向总分。
- OpenCV 与 SciPy 只用于本地校准/转换，尚未进入 V4.9 runtime 或 Release；当前发布依赖
  仍为 NumPy、tifffile、imagecodecs 与 Pillow。
- 最近的 tracked test 审计未发现重复 test body、空 test module、未使用 public support
  owner 或无静态 incoming owner 的 active Python module；不做猜测性删除。

## 精确下一步

1. 定义 production output 到 confirmed source-coordinate polygon 的只读比较合同，纳入
   现有 deskew mapping。
2. 不先调参，测量八张 `nominal_calibration`：逐边 signed normal distance、angle、
   unsafe outward crossing、inward content loss、containment、status/reasons 与
   geometry resolution。
3. 只从 nominal subset 推导方向性验收容差，再单独验证 `S098`。
4. 由一个 focused failing contract 定位第一个 production gap，修复 canonical owner，
   比较 current-schema report 与 Debug Analysis，最终 full 验证交给 push Hook。

恢复时先运行：

```bash
git log -1 --oneline
git status --short
python3 -B Test/manual_review/red_markup_converter.py verify
wc -l Test/manual_review/manifest.jsonl
wc -l Test/manual_review/red_markup_fit_proposals.jsonl
wc -l Test/manual_review/user_confirmed_golden_baseline.jsonl
rg 'REPORT_SCHEMA_REVISION' x5crop
```

恢复提示：

> 从 9/9 user-confirmed 黄金基线继续：8 张 `nominal_calibration`，S098 为
> `irregular_geometry_stress`。先建立 production output 到 confirmed 原图 polygon 的
> 只读方向性比较，不先放宽 detector；随后用 named TIFF、current report 与
> Debug Analysis 定位第一个真实 gap。
