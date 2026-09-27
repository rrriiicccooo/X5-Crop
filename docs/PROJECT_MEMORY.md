# 项目记忆

更新：2026-09-27。现场 Git、原 TIFF、source SHA、current report 与最新验证高于本文件。
长期合同见 [ARCHITECTURE.md](ARCHITECTURE.md)，人工权限见
[MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md)，协作规则见 [AGENTS.md](../AGENTS.md)。

## 当前目标与执行顺序

已从暂停的“V5发布”会话 `01a07f23-208e-7871-ab28-65270d32dc9e` 交接至
`01a0e15e-4384-7972-9455-cd3a9af52ee0`，后者持有持续目标；不唤醒前者。

1. 先完成 H，验收对象是最终安全、留边合格、直接可用的裁切。当前优先识别外侧大面积纯色、低纹理
   或规律纹理片夹区域，再沿其内缘保留照片。保护给定 TIFF 中已经记录的可见内容，不恢复被片夹
   遮挡且没有记录的内容；人工黄金源内 polygon、逐侧 5% 上限及倾斜角点保护仍有效。
2. 区域身份、内缘位置、方向、H 与输出预算在现有模型和联合求解中闭合。低纹理或外侧位置本身不能
   证明片夹；照片贴到源边时不能凭空建立背景种子。允许无害不确定性，不为已可用样片继续精修。
3. H 验收后继续 W 的逐张左右边归属、间隔、接触、重叠与截断，再完成此前全部能力和下文延后审计。
   H 阶段冻结无关 W 算法修改；既有 W 与放置模型仍可约束 H。
4. 最终当前 development nominal 全部正确 `approved_auto`，所有角色
   `unsafe_approved_auto = 0`；challenge 尽量安全自动通过，安全 Review 不替代 nominal 能力。
   当前 cohort 为 110 task / 106 source，其中 nominal 96、challenge 14；数量以冻结 cohort 核对。
5. 完整用户路径 24-source 平均 `<=5s`，`<=3s` 为持续挑战目标。正式性能留在发布验收；
   工程、黄金、TIFF/metadata、安装、三目标实机、打包与 Hook/CI 都绑定同一最终提交。
   达到发布标准后仍由用户确认发布，不提前创建 RC、tag、Release 或公开 ZIP。

保持 current-only、唯一职责，无旧兼容、样片特例、隐性 fallback、放宽黄金或提高预算。
新机制须改善最终输出或解决具体证明缺口；只增加峰、解释数或中间精度不是整合依据。
同源 task 按 source SHA 组织研究；黄金只用于离线研究和评价，不进入运行时选边。

## 当前源码与验证身份

- 交接基点为 `0c4ecbb7199fdc048ae803a1db14bb7d965d196d`。
  暂停会话的干净检出 `/private/tmp/x5crop-h-output-20260927` 已复用；此轮检测器未修改。
  该检出的 detector manifest 为
  `c859a4ca7fec8b78441bacb78d4db256d83535397736ee6227582cfe89f99328`，
  comparator manifest 为 `be79bfe58936b7c78c717a619536c597fcd2b8a6b7f61444f6da69d81a6f136d`。
- 主目录仍保留 31 个 tracked 未暂存修改和 2 个 untracked 文件，属于此前未验收的逐 trace broad
  测量/有界关联及其报告、Gate、三维顶点去冗余配套修改。它们不是本轮片夹区域识别实现，未覆盖、
  reset 或删除。两目录即使 HEAD 相同也不是同一检测器，不混用其 receipt。
- 旧 `h_direct_pair_use_full_20260923` 记录 21 safe auto / 0 unsafe auto，其 detector manifest
  `9157d7ca49fee662910997fb608ef33c6a6e60b6a239bdcf9d988ac6eef296da` 与当前干净源码不同，
  只能作为历史比较。旧 broad 原型完整诊断的 16 safe auto / 0 unsafe auto 也不是当前接受结论。
- 当前完整基线通过新增薄路由执行：
  `tools/verify diagnostic --gold-analysis --output-root <path>`。它复用原 gold_analysis owner、
  正式生产执行和原 comparator，默认 report gate；`accuracy` 的完整发布 gate 保持。
  产物目录为主目录 `Test/gold_analysis/holder_region_baseline_20260927`，
  运行日志为 `Test/gold_analysis/holder_region_20260927/production_baseline.log`。
  已完成 110/110 项，analysis error 0，全部 current report 与物理校准通过；21 safe auto、0 unsafe auto，
  nominal 仍有 75 Review，challenge 14 项均 Review。与旧完整记录的 proposal/candidate 安全标签和
  最终决定逐项一致。该结果是当前源码绑定的开发基线，不是 H 验收或发布性能结果。
  保留方案中 47 个任务至少有一份整组合格方案，63 个尚无；不能把存在合格方案等同可靠自动选择。
  隔离检出使用独立 inode 的 APFS TIFF 副本，源身份由正式验证核对；不用指向主目录的 Test 符号链接。
- 此轮实际 import：Python 3.14.7、NumPy 2.5.3、SciPy 1.18.1、OpenCV 5.0.0、tifffile 2026.9.20、
  imagecodecs 2026.8.16、Pillow 12.3.0，与当前依赖合同相符。入口为 `/opt/homebrew/bin/python3`。
- 当前合同为 report 91。已有共同 H 输出、直接 aperture 用途及预算保护均保留；
  H 尚未验收，W 与正式发布性能仍后置。

## 当前片夹区域证据

全部 106 个源的固定原生 RGB 外侧测量已完成，覆盖同源 110 个任务。脚本、数组、source/cohort SHA、
逐点评估位于 `Test/gold_analysis/holder_region_20260927`；
方法、反例和权限见 [BOUNDARY_FEATURE_RESEARCH.md](BOUNDARY_FEATURE_RESEARCH.md) 的
“片夹区域与可见内容保护”。它是材料假设研究，不是新的检测器或 H 通过凭据。

S064 的外侧材料提供了位于黄金指导线外、留边合理的提示；强亮照片与白色片夹连通、照片已贴到源边
分别由 S047、S106 暴露。固定颜色前缀门槛全部存在反例，不能直接生成排除 mask。
已进一步完成全部 106 源的正式 CLI 灰度捕获；106 个代表请求的 primary footprint 和 decision
与完整基线一致，当前运行时仍未改变。完整原生灰度、report、source SHA 位于上述目录的
`registered_gray/`，无须重读全部 TIFF。四个同源 count 变体的注册测量尚未单独捕获。

全列密集区域与凸包外框研究已完成：110 task 的 H 半平面检查为 75 满足、27 外扩超限、8 区域不可用，
内切 0。再保护全部已注册 H binding 原始区间后，106 个代表请求为 71 满足、28 外扩超限、
7 不可用，内切仍为 0。这些不是生产裁切通过率或 safe auto。
合成弱前沿反例证明仅靠颜色区域不安全：会内切 86.578 px；保留独立原生弱 sharp 区间后退到前沿外
7.5 px。既有弱证据不能被区域标签覆盖，逐 trace 真坐标和完整物理线族保护仍是接入前提。

将区域已获权作为明确反事实、保留原有全部 Cross 竞争后，现有 owner 对 S062/S064/S067 均产生
黄金 safe 且全部预算通过的完整输出；S064 TOP/BOTTOM 预算约 77.523%/73.376%。
S003 原唯一 aperture 保持不变。证据为 `protected_enclosing_feasibility.json`，它使用明确标识的
synthetic certificate，只证明输出通路可行，不证明材料身份、真实 observation 或自动批准。
凸包编译器与 LP 目标、完整约束、翻转及平移的 100 组检查通过；它仍是忽略目录中的研究实现。

## 精确下一步与开放风险

1. 当前完整基线和输出分类已闭合：21 项安全 auto；19 项 H 已满足、阻断在其它部分；33 项 H 几何
   失败；23 项 H 预算证明失败；9 项共同输出或权限待闭合；4 项联合角边失败；1 项长轴未生成 primary。
   新 `output_triage.json` 复用原 classifier 与 comparator，绑定本次完整运行；后续只围绕实际输出失败
   增加 H 机制，不重新泛查已有合格 H 的 40 项，不把 Review 总数当作 H 失败数。
2. 下一项是把已证明有输出潜力的密集区域机制做成可核验的 typed producer，而不是继续搜索更多颜色
   门槛。先关闭区域与弱 sharp/broad 原始证据冲突、完整物理线族与局部偏离的保护；合成弱前沿必须
   保持安全，材料种子不成立时保持 unavailable。8 码、5×5、0.25 mm 是当前固定实验参数，尚未取得
   生产权限；不以全源无内切的开发结果代替反例、实际注册和完整运行。
3. 复用 coarse/Cross/现有 enclosing 输出；构造线必须与实测 transition 语义分开，不授予 placement
   或 deskew 角度权限，不把 synthetic certificate 接入生产。完整源的所有点均已测量，不按 winner
   重读；缺少 departure 的列受测量带边界约束。凸包编译替代研究 LP，登记实际像素、临时内存和几何
   工作量，再补 report/Gate 回链。现有唯一 direct aperture 继续保留原权限。
   接入后用正式 CLI 和冻结黄金验证 110 task，保留 21 个 safe auto，危险 auto 必须为 0；
   分别报告 H、整组合格和可靠 auto，不能用反事实的 safe 输出冒充真实进展。
   不增加按 canonical W domain 截短区域的接口：它不是完整物理保护域，且目前全源方案已有潜力。
4. 主目录待验收 broad 修正另有明确真实问题：区域均值会偏移代表坐标，逐 trace 关联原型又暴露
   搜索超界和输出回退。需要在当前唯一机制内关闭真实坐标与完整关联职责；不能因为此轮另研究片夹，
   就接受旧伪代表点、清除合法竞争或遗忘未验收修改。当前失败与收益须用对应 manifest 重新验证。
5. 公共中英文手册与架构已补充可见内容范围；上一文档与 diagnostic 薄路由提交为 `e668b364`。
   当前新增实验只在忽略目录，生产源码和权限未改。研究结论与本检查点按正常 Hook 提交、推送；
   保留主目录其余修改，不推送混杂的未验收源码。每项实现验证和 Git 交付按 AGENTS 执行。
6. 发布仍需同一最终提交的全部验收，三目标实机 receipt 未在此轮完成。当前没有 sealed cohort，
   黄金未覆盖 xpan、120-645、135-dual；按架构披露这些边界，不据此新增禁用规则或假称泛化合格。
   概率选择若启用，另须其独立 calibration/sealed 合同；本轮未启用。

## 延后任务：共同 W 与逐 Frame 真实变化审计

启动条件：此前已确认的全部能力完成后再开展，不打断当前工作，不提前实施，不据此回退正确改动。

审计问题是区分“各 Frame 围绕 source 共同 W 有经过校准的小幅真实变化”和“全部 Frame 共享同一个
尚不精确的 W”。扩大共同 W 区间不必然等价于允许逐 Frame 变化。侧会话提供的三条线索——source W
估计容许 residual 并传播到 W、双侧/单侧/无直接边的投影方式不同、完整未观察 Frame 调用整条 sequence
联合约束而可能暴露远处冲突——均是待验证机制，不是已证明的样片根因，也不授权放宽 Gate。

1. 区分测量误差、真实 aperture/走片变化与模型误差，核对各自 canonical owner。
2. 以最小正反例和少量真实样片，验证三种投影是否遵守一致物理合同。
3. 仅在开发测试的 solver 输入隐藏指定 observation；原 TIFF、测量记录和黄金不变，检查几何跳变或
   无解是否合理。测试实验不得成为平行 production path。
4. 若确认问题，优先复用共同 W、local correction 与联合 uncertainty；只有证据证明必要时才设计
   经校准、有界的局部变化合同，不增加样片特例，不隐藏反证。
5. 作为独立小机制闭环完成全部黄金与相应工程验证；正式性能在发布验收时验证。
   当前仅登记，不调整物理模型或验收标准。
