# 项目记忆

更新：2026-10-18。现场 Git、原 TIFF、source SHA、current report 与最新验证高于本文件。
长期合同见 [ARCHITECTURE.md](ARCHITECTURE.md)，人工权限见
[MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md)，协作规则见 [AGENTS.md](../AGENTS.md)。

## 当前目标

先使既有样片与本机项目达到完整发布标准，再安排新增扫描和其它平台实测；达标即停止等待用户确认，
暂不发布。验收最终逐格对应、完整画面保护、固定尺寸、源域和风险预算，不要求内部角色与人工同名或
解释唯一。优先解决已有几何合格且预算通过方案的选择与准入；共同输出须覆盖完整竞争集合，逐成员
核验自身尺寸和权限，不能借 primary 权或让黄金参与选框。S053 不预设为接触案例。
保持全部几何方案覆盖和零危险自动批准；5 秒均值为 Gate，3 秒仅为 challenge。净收益分别报告首选
几何合格、几何加预算通过、安全自动批准及逐 task 回归；候选覆盖和测试通过不替代发布能力。

## 当前证据

### 黄金与 Review

最新完整报告为 `Test/engineering_audit_20261018/gold_orientation_current/`：110 task / 106 source
全完成、无分析异常。与上一检查点及本轮首轮逐 task 比较，除耗时外完全相等；首选、预算、auto、保留
几何及权限无回归，见同目录上级 `orientation_full_gold_equivalence.json`。
方向视图、竖向灰度视图和非连续 RGB 采样已验证，报告冻结 runtime／比较器／cohort 身份；
不把开发黄金或同字节核对当作最终发布验收。

| 项目 | 最新结果 |
|---|---|
| 至少一份黄金几何合格保留方案 | 110 / 110 |
| 首选 proposal 几何合格 / 不合格 | 94 / 16 |
| 首选几何合格且数值预算通过 | 66 |
| 安全自动批准 / 危险自动批准 | 26 / 0 |
| nominal 自动批准 / Review；challenge Review | 26 / 70；14 |
| `release_detection_gate_ready` | `false` |

84 个 Review 的当前输出分组见 `Test/release_readiness_20261016/current_output_groups.json`。
完整 typed 交叉表在同目录 `final_output_inventory/`，明确绑定修改前的 1583f010；S086 已移至 auto，
其它任务不变。这些保留方案库存不冒充完整竞争池：

| 互斥分组 | nominal | challenge |
|---|---:|---:|
| 首选几何合格且预算通过 | 36 | 4 |
| 仅其它保留方案几何合格且预算通过 | 15 | 4 |
| 所有几何合格保留方案预算均失败 | 19 | 6 |

第二组只有 8 个 nominal 的首选实际几何不合格；其余 7 个首选已几何合格但预算失败。第一组的
phase／Cross／最终阻断交叉表完整保存，不能把 ambiguity 名称直接解释为多余阻断。

### 选择机制与共同输出

- S086 的首选遗漏唯一获权 separator 伙伴，结合本候选原生另一边要求 W 至少 3934.2235 px，超过
  原模板物理上限 3743.0271 px；旧首选与备选的第 2 格共同保护也超过固定框 170.4669 px。
  全部 26 条 canonical 记录中只有原首选命中此反证，原完整证据与可重放源码在
  `Test/release_readiness_20261016/S086_selection_audit/`。
  新检查在压缩前对称核验全部成功投影；不绑定伙伴、不调排序、不借 W。原冲突解释保留为 terminal。
  正式 CLI 和完整黄金确认 S086 首选合格并安全 auto，自己的 W 为 `reconciled_direct_constraints`；
  S068 保持 safe Review。首选合格和安全 auto 各净增 1，无对应回归，专项证据为同目录
  `S086_approved_current/` 与 `S086_new_projection_receipt.json`。
- 当前 CommonH 只证明同一已解析长轴模型下的完整 H 竞争。基线第一组有 8 个窄 phase 入口；
  S005/S006/S026/S075/S081 的保存主备均几何合格且预算通过，尚无完整共同输出准入证明。
  S005 当前官方 CLI 的完整原始投影为 50 条：32 条未获准、14 条成功但在原 holder 范围外、4 条
  canonical 成功。不能把 canonical、未胜出或支持较少当作完整物理反证集合。最新逐份审计从初始
  source H 与各自 W 重放全部 18 个成功投影的注册 Cross 输入，实际共 630 次 evaluated fit。
  四份 canonical 都凭自身证据选择同一直接 aperture pair，H 与比例相容；固定长轴尺寸仍分为
  3452.1372 / 3418.7325 px。证据为 `S005_complete_phase_cross_authorities_accepted.json`，绑定
  5c62d6f7 与原 TIFF，报告校验通过；这是离线核验，不增加生产预算，也未证明完整成员／局部精修闭合。
  旧四份 ordered 保护并集能放入较小框、最紧余量 46.2659 px，仅是必要几何条件，见
  `S005_own_size_necessary_geometry.json`；测量区间相交不授予共同尺寸，不据此晋升。
  若把源端 Review 的另一 ordinal 映射也并入，第 2 格至少需 6392.6204 px，超过原格式最大固定框
  3656.3414 px，见 `S005_ordinal_common_window_necessary_counterexample_accepted.json`；这不否定
  四份 canonical 的共同输出可能性，也不把缺全局权限的 Review 映射改称自动准入成员。
  S011 只有一份已生成 canonical 输出，但完整池有 6 ordered / 4 terminal；更高支持的原生竞争
  与校准 Grid 冲突，不能删除。逐成员必要权限核验见同目录 `S011_phase_member_authorities.json`。
- S082/S093 的两个 continuity 均 supported；最终 topology 阻断来自未独立闭合的两点 pitch 假说。
  撤权后已恢复原模板，phase/pitch authority 为空；材料本体仍参与正式竞争。原假说核验中，S082
  的 6 份投影均 Grid conflict，S093 的唯一可行投影缺少两 band 之外的独立 anchor。该限定核验不能
  证明完整最终输出。逐成员审计见 `S082_withheld_pitch_member_audit.json`、`S093_withheld_pitch_member_audit.json`；
  另有 `S082_complete_phase.pkl`、`S093_complete_phase.pkl` 保存全部原始投影及 lattice 作用域。
  正式竞争的原始投影为 78 / 6，canonical 仅 31 / 2；新观察工具未改变正式几何与决定，源码和原 TIFF
  已核对，见 `withheld_pitch_complete_capture_acceptance.json`。
  不把受限 refit、canonical 子集或未使用的 pitch 参数直接当作解除阻断的证明，暂不新增准入路径。
- 既定 primary 尺寸的完整池必要几何筛查使 S006/S026/S075/S080/S081 至少一格放不下；
  S080/S081 全成员 late refinement 后仍不成立。它不否定所有跨模型共同输出，但 source-W supported
  子集不代表完整竞争。入口为 `Test/release_readiness_20261014/common_window_*replay.json`。
- Cross 阻断中，S002 有局部多选，S015 缺纵向权限，S028/S045 完整归属搜索所需拟合已超原预算；
  仅优化枚举不能回收准入。证据为 `Test/release_readiness_20261015/common_h_closure_audit.json`。
- S040 的 `side-region:139` 已进入正式 profile，但六点物理直线域为空；原 recovery 删除 3999 后
  只剩两区域且连续支持断开，拒绝正确。同一完整查询另有一份物理可行、三区域连续的 START 关联，
  被互为唯一最近邻排除，见 `Test/release_readiness_20261016/S040_sharp_association_scope_audit.json`。
  通用关联补全虽使 S040 首选合格且预算通过，完整黄金却使安全 auto 26→5、几何覆盖 110→96，
  并出现 2 个合同错误；定向修正后仍有 3 个 auto 退回与 2 个错误，整项实现已撤下。
  反例与补丁保存在同目录 `sharp_association_*rejected*.patch`、
  `sharp_association_full_regression_rejected_corrected.json`、`sharp_association_selected_support_rejection.json`。
  不仅为增加路径数重开；新机制须改善最终输出或提供独立安全依据，不能删竞争、恢复 139、扩阈值或借 W。
- 评分仍为离线研究，`admission_enabled=false`。source 分组 OOF 98 safe / 12 unsafe 不代替独立
  calibration；错误方案预算通过、合格方案预算失败的反例仍存在，不硬化代理阈值。

已收束的无净收益方向：完整 phase 预补全、residual 舍入、S042 原生／RGB／宽缓与 raw-family alias、
全面反向峰、取消聚合材料角色过滤。证据保留在 `Test/release_readiness_20261012/` 至
`Test/release_readiness_20261015/`，不重复同一调参。S053 在现映射下的 native 等 pitch 区间不相交
只证明这份解释有约束缺口，不证明真实胶片不等 pitch，也不把内部角色命名差异作为失败。
匹配中心缓存与空／单元素支配快路径在串行完整 CLI 对照中没有稳定收益，已撤下；exterior median
转置也无收益。证据在 `Test/engineering_audit_20261018/matching_ab.json`，不重复同一微调。

### 性能与环境

本轮正式性能待代码提交后重测；旧 `97daa7fc` receipt 不代表新版源码与依赖。隔离完整 CLI 对照确认：
竖向灰度视图使四张样片 peak RSS 中位值降低 23–54 MiB；方向视图配合平坦百分位采样，使 S101 持平，
S105／S106 分别降低约 200／214 MiB，报告与 TIFF 字节均相等。证据为
`Test/engineering_audit_20261018/workspace_view_ab.json`、`orientation_flat_ab.json`；它们不代替正式计时 Gate。
现场 pip 加载 NumPy 2.5.4、SciPy 1.18.1、OpenCV 5.0.0、tifffile 2026.10.15、imagecodecs 2026.10.10；
Pillow 12.3.0 来自 Homebrew。冻结合同已同步，保留本机新版；跨环境差值不归因于单项源码或库。
本轮删除重复解码、退役函数与重复测试夹具，Python 净减少 161 行；10 份文档已审计。
仍有 14 个生产模块超过千行，phase／Cross 编排和外部校验器保留较大函数，不声称已经达到全局最优。

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

## 开放风险

- nominal 尚未全部安全自动通过；全部保留几何覆盖不代表首选、资格或发布 Gate 已完成。
- gold 未覆盖 xpan、120-645、135-dual 真实样片，也没有 sealed cohort，不声称未见来源泛化。
  若评分承担自动准入，仍须独立 calibration、冻结风险／OOD 合同与 sealed acceptance。
- 用户已确认可安排 Intel Mac、Windows x64 实测和新扫描人工确认；按其要求先完成现有／本机。
  最终全部资格须绑定同一 release commit；没有发布授权。

## 精确下一步

1. 继续优先第一组有合格输出却未准入的通用机制，研究完整 phase／Cross 竞争的共同输出；
   保留原生成员、terminal 反证、各自 W/H 权限与完整预算，不把全部角色修正作为前置目标。
   S005 的注册 Cross 逐份核验已完成，准入仍缺完整成员与共同尺寸权限；无证明前停止该方向的实现。
   S082/S093 先核对邻接阻断是否确实影响完整输出，
   使用完整原始投影与每份自身权限，不因首选几何合格或预算通过而删除 topology 证据。
2. 识别精修只服务已证明的输出／权限缺口；S040 的一致关联补全因整体回归已收束，不再仅按路径数量
   扩大该机制。只有能改善最终输出或提供独立安全依据的新证据才重开；不把内部角色修正作为前置目标。
   本机达标后冻结最终提交，补齐其它平台验收；
   达标即停止等待确认，暂不发布。
