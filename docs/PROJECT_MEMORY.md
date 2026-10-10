# 项目记忆

更新：2026-10-10。现场 Git、原 TIFF、source SHA、current report 与最新验证高于本文件。
长期合同见 [ARCHITECTURE.md](ARCHITECTURE.md)，人工权限见
[MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md)，协作规则见 [AGENTS.md](../AGENTS.md)。

## 当前目标与授权

持续目标是让 V5 达到发布标准，保持 current-only、单一职责和零已知危险自动批准。
用户已授权整理代码、测试、全部文档与项目记忆，并将未提交、未推送的工作提交推送到 `main`。
发布仍须用户另行确认；不提前创建 RC、tag、GitHub Release 或公开 ZIP。

裁切使用 source 共用 W/H 的固定 `1.1W × 1.1H` 请求窗口，5% 留边包含基础保护。程序只选择位置；
完整可见内容与合法物理保护无法放入时保持 Review。框内偏移和实际向外距离不另设逐侧上限。
完整物理状态、证据权限、source/lane 安全与人工 reference 不变，精确合同由架构拥有。

## 最新完整黄金证据

最近完整 development gold 为 `Test/gold_analysis/fixed_output_20261008_final/`，绑定
`1a92bbcf8f3f74563f192f7b90b5f9ce962228d4`，不是此后清理提交的发布证书。
`gold_analysis_summary.json` 记录：

| 项目 | 结果 |
|---|---|
| task / source | 110 / 106 |
| nominal / challenge | 96 / 14 |
| 完成 / 分析异常 | 110 / 0 |
| 安全自动批准 / 危险自动批准 | 23 / 0 |
| nominal Review / challenge Review | 73 / 14 |
| 首选提案安全 / 不安全 / 未生成 | 81 / 28 / 1 |
| 至少保留一份安全提案的 task | 90 |

源码身份与物理先验校准检查通过，`release_detection_gate_ready=false`。
保留集合不是全部潜在几何解释；90 项有安全提案不意味着这些提案已获得 Runtime 自动权限。

证据身份：

- detector manifest：`ca1a0a9c822464ca62ba6a70e27403343d8cb8c02888f39ad5bd4c19e4e2bc08`
- comparator manifest：`911e23f8e60b72c037f02c0f8f8498ab8f90f4b263020174d6dca21603a848f9`
- development cohort：`daaea2ad49564616342051253c8fa67c4922a260d0dcc92f0d187f7b2eb10288`

工程检查、黄金准确性与发布资格分别验收；死代码和文档清理不重标旧黄金或性能 receipt。

## 保留的人工局部事实

用户已确认以下 Orientation=1 原 TIFF 半开坐标窗口的材料语义：

- M1：S064 `[0,8845,330,9445)`；M2：S064 `[2450,7172,2797,7772)`。黑色为外部材料，其余为照片。
- M3：S006 `[1975,2309,2615,2797)`。白色为外部材料，其余为照片。

记录位于 `Test/gold_analysis/material_identity_gap_20261002/review/human_semantics_20261002.json`，
SHA256 为 `c3d8fdbafc29e93fb0828f1cd90191697713bafa86ffe199f948d55535d00994`；其中绑定原话、
source SHA 与窗口像素身份。不再重复请求这三窗确认。精确过渡坐标仍未确认，这些局部语义不授予
通用颜色分类、pixel mask、全源连续性或黄金 reference 权限。

另有已确认的展示窗口事实：`bounded_competitors.png` 中 S047/S003/S064 蓝线接触准确，S016 不准确。
窗口映射为 `Test/gold_analysis/gold_boundary_features_native_20260921/bounded_competitors.json`；
交付图 SHA256 为 `13cac1b104ba68ade9e45687c1e1e7c5ec1ee00c170a75b905832f02598a085a`。
JSON 只证明窗口映射，人工确认仅限展示范围，不扩展为整源或改写 gold；S064 旧窗不覆盖 M1/M2。

固定 RGB 前缀与仿射 seed 外推已被反例否定，不继续围绕同一失败假设调阈值。
反例入口与材料测量权限统一见架构第 5 节，原始证据保留在 `Test/gold_analysis/`。

## 开放风险与下一步

1. 按当前报告区分提案生成、候选资格和最终选择。先修不安全提案的通用几何，再审计安全提案为何
   阻断；不以最高分、删 runner、改评测角色或放宽保护制造自动覆盖。
2. H、W、phase、anchor 与邻接可以独立推进，不再设 H 完成前禁止 W 的顺序限制。共同 H 必须证明
   完整成员与全部局部精修闭合；共同 W 多重归属尚未获权，不能把 best/runner/conditional 当作完整解释集。
3. Runtime 评分选择尚未启用。独立 calibration、sealed acceptance 与风险准入仍缺失；当前折外排序
   只用于开发研究，不能代替正式概率权限。
4. 当前 gold 尚无 `xpan`、`120-645`、`135-dual` 真实样片，尚无 sealed cohort，不能声称这些覆盖或未见
   来源泛化。按架构保留明确披露，不建立 format 特例。
5. 准确性完成后，正式性能、TIFF/metadata、安装、三目标实机、打包与 Hook/CI 须绑定同一最终 release
   commit。旧性能结果不能用于当前版本签收；Intel Mac 与 Windows x64 暂不可用是用户已确认的发布阻碍。

用户要求的“共同 W 与逐 Frame 真实变化”审计延后到此前能力完成后开展。届时区分测量误差、真实
aperture/走片变化与模型误差，以最小反例检查不同边界可见性下的联合投影；当前不增加逐 Frame
尺寸自由度、不改变物理模型或 Gate。
