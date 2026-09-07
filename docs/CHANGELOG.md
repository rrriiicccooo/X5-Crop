# X5 Crop 更新日志

本文件只记录版本级行为与验证边界。当前合同见
[ARCHITECTURE.md](ARCHITECTURE.md)，当前检查点与风险见
[PROJECT_MEMORY.md](PROJECT_MEMORY.md)。开发中的逐次 schema、样片统计与命令记录保留在 Git history，
不作为当前版本合同。

## V5（当前开发版本，尚未发布）

### 产品行为

- 用户提供 format 并确认默认或显式 count；空白曝光格保留 ordinal。Runtime 不猜格式、照片数或 blank，
  不提供历史 mode、平行 detector 或兼容入口。任一 slot 不安全时整张 source 进入 Review，不做局部输出。
- 校准 Grid 是唯一 placement 主生成模型。Format/count 编译有界 W/H/pitch，直接 absolute anchor 定位，
  native boundary 与 Separator/Contact/Overlap 修正局部关系；缺边和完全未观察 Frame 使用同一相关模型。
  片夹中心、拟合 residual 和 Grid 自身不能冒充像素权限。直接事实、coverage、反证、联合包络与预算分别负责准入。
- 已在 v4.2.8 真实样片中有效的整条片带观察、outer/cross、separator、deskew、候选无关复用与 TIFF 保真
  迁入 current owner；删除未经校准的终判、事后改边界、任意 fallback 与旧源码结构。
- Dark/light separator、共享边 material component、局部 aperture domain、source 端部窄材料带和 Cross
  纵向覆盖分别保留 typed 权限与反证。局部线不能越过未观察区域取得整条片带的输出权限。
- Cross 单区域片段保留为测量与角色假设，完整 family 并集达到原有两区域要求后才可获权；
  模板覆盖数不提升原始测量支持。未获权假设不移动边界、不充当外侧反证，也不阻止已有有界缺边精修。
  完整测量账本与全局 solver 输入分别计数，局部假设不占用全局边界配额；原 producer 与求解上限不变。
- 源边或查询范围截断的定位峰不再以可见峰尾取得精确坐标；宽缓材质峰同时检查双尺度实际可观测域。
  完整峰、极性分区和窗口 ownership 保留既有职责，不增加像素读取或放宽测量阈值。
- Top/bottom 共用预登记的 lane 完整短轴归一化基线，保留原查询窗口与测量阈值；基线不产生边界证据，
  也不补造源边缺失观测。两轴基线按组顺序消费和释放，完整像素工作及整组缓冲进入原有预算。
- 端部窄材料带保留内侧边界假设，但不再仅因窄带存在而否定外侧 edge 的独立角色权限；材料可能处于
  aperture 内。W/ordinal、独立证据和后续风险条件继续约束解释，不强选更内侧边界。
- 唯一且获权的实测窄 separator 可以原子闭合相邻角色，不再额外要求 gap 达到 nominal 下界；既有
  材料权限、正常间隔上界、W 与竞争条件不变。候选投影按新的实测关系重算 constraint rank，降秩时使用
  已有校准 Grid 或保留不可用，不能沿用旧 nominal rank 丢弃合法候选或取得满秩权限。
- 直接与校准 Grid 重拟合共用当前 phase-anchor 残差相容性判定；旧模型的失败或成功不传给新几何，
  local refinement 不稀释或抬高全局均值。原阈值、native binding、总 residual 特征与预算保持不变。
- 唯一 source-wide material pair 保留 endpoint 已有的像素角色候选，不以间隔解释覆盖原角色。
  两种解释共用同一 observation/component，继续接受原有全局约束、直接权限和候选竞争检查。
- 纯离散歧义下，已有 primary/runner 分别补全原有局部边界，并各自投影晚期弱线、保留硬反证；
  不共享 selected source W，不增加 phase 搜索，不改变歧义、候选顺序或批准条件。
- Cross 支撑区间在纯离散歧义下分别保留 primary/runner 两组；同一横向边界逐组满足原有覆盖要求。
  候选不合并几何或增加独立票数，登记与 refit 不重复，未闭合的纵向歧义继续进入 Review。
- 已满足共享支撑与纵向覆盖合同的直接 Cross pair，不因某侧新增 source-spanning 连续性而降为
  单侧 H 推导。未闭合的局部 opposite、多个合法 pair 与外侧反证继续按原条件处理，不放宽阈值。
  候选选择、反证与最终授权复用同一 pair proof，消除局部互补 closure 漏记反证的问题；
  完整 pair 仍作为合法方案参与竞争，多个完整方案保持歧义。
- 纯离散歧义的 primary/runner 分别以自身合法直接约束收紧 proposal 联合包络；runner 不借用 primary
  的角色或不匹配的 source W。歧义、反证与输出资格不变，空可行集明确保留为 unavailable。
- Enclosing aperture-center 校准按当前唯一 selected pair 的 18 个 source 重登记观测指纹；
  原资格、source 中位数、全体 hull 与向外量化方法不变，当前区间为 `[-0.008H, +0.010H]`。
- Source W 明确分开测量、placement 消费和自动输出资格。至少两张合格完整 Frame 或全部独立 rank-3
  直接约束可建立测量；两组都成立时只取交集。远处 coverage、全局 rank 缺口或 unresolved proposal 不再
  抹去合格局部测量，反证与 runner 仍保留。W 不重选 phase/ordinal，不增加独立 rank。
- 消费 W 时保留仍可行的原联合代表；确需改变 W 时，同步更新派生 gap、local delta 与角色区间，直接坐标
  不变。弱局部角色让位后，其旧坐标区间同时退出约束，其余联合投影保持。完整未观察 Frame 不阻止其它
  单边 Frame 的相关 W 推导；其本身仍由 Grid、coverage、反证和联合几何负责。
- Source W 经校准比例只产生一份相关 H；直接 H 优先。比例不可用时，合法单侧 Cross 可由有界 format H
  推导 opposite。Enclosing support 的中心偏移按同源黄金校准，不能把外侧材料线冒充 aperture。
- 完整 pre-Gate proposal、candidate eligibility 与最终决定独立。权限或竞争尚未闭合时仍保留已有完整
  Review proposal；它不冒充 approved sampling geometry。概率可接受性评分目前仅有开发合同，尚未接入 Runtime。
- 输出以同一联合状态传播 uncertainty、residual、bleed 与 topology protection，逐侧共用原有 5% 预算。
  真实 TIFF 截断与内部 lane 越界分开；不通过裁小请求、扩大 bleed 或混合互斥状态获得批准。
- 真实 TIFF 外缘统一为首末像素的单元边界，恒等采样完整保留首末行列；只改变源域交集，
  不普遍外扩照片边界。连续 polygon 与整数采样 box 分开表示，内部 lane 仍按原权限阻断。
- Deskew 仅整理已批准结果，不参与 placement 或黄金判定。正式 TIFF 保持 16-bit RGB、ICC、resolution、
  支持的 metadata 与无损压缩，写入 Orientation=1；整组 staging 完成后原子发布到新目录。

### 报告与验证

- Normal report 与 Debug Analysis 只显示同次检测事实，分开 proposal、candidate、正式输出、runner、
  typed failure、calibration identity 和实际工作量，不重新检测或求解。当前 Report revision 为
  `x5crop_v5_template_report_73`，登记两轴归一化身份并检查基线无证据、完整范围与工作账本；
  逐候选记录 Cross 支撑区间、覆盖序号和真实 source extent，不保留旧 schema 兼容层。
- Cross 每条直接边界保留原始独立区域数；开发校验回链原 query/transition、registered binding 与
  各候选的角色权限。Coarse enclosing track 继续只有外侧几何支撑权限，不冒充照片边界。
- Source extent 同时绑定 input、Orientation、measurement、全部候选与 final sampling；源截断类别
  由实际源尺寸复算。Final polygon 复用 selected geometry，采样 box 从同一 affine 与 polygon 重建，
  不以整数采样框替代严格黄金包含检查。
- 报告校验接受已有的 `direct_lattice_conflict` 投影失败，继续要求 unavailable authority、
  完整被投影角色和明确失败原因，不改变 Runtime 或批准条件。
- 黄金集合统计支持只有 runner 能物化的情况，保留原角色，不伪造 primary 或将缺失几何计作负例。
- 每条 lane 保留已有 best 与单个 runner 的完整 proposal 或 typed unavailable；每份由同一输出 owner
  物化一次，正式输出复用 primary。新增投影次数与逐 slot 输出评估次数，不扩大候选搜索或自动权限。
- 每份 proposal 保留同一 owner 的数值预算和 28 项带单位、provenance 与 missingness 的物理特征；
  正式 candidate 复用 primary 预算，不重复计算。缺失不记为 0；锚点按独立 evidence group 去重。
- 离线开发排序按 source SHA 分五折，同源 count 不跨折；训练集内标准化和固定 ridge 拟合不读取
  样片身份或 cohort 特征。多正例与 unavailable 分开处理，独立报告折外与样本内结果。排序分数不是
  可用概率，数值支持诊断不是正式 OOD，不改变 Runtime 或自动批准权限。
- Development gold 分开比较 proposal、candidate 与 approved output。Runtime 的实际数值预算评估和
  CandidateGate 的预算阻断分开统计；未评估不能冒充通过。比例 H 的预算诊断只记录实际消费和阻断事实。
  每份保留候选独立记录最终 footprint 与方向性黄金标签，允许多份同时安全；无法生成不算不安全负例。
  集合统计区分单份安全、多份安全、全部保留候选不安全和存在未能评价的候选，并对照每份 proposal 的
  数值预算。Gold record / summary 为 v20 / v23。
- 人工 reference 只来自原图坐标中的用户确认或独立外部测量，绑定 source SHA；模型与自动工具只产生
  proposal。Comparator 对原图黄金执行一次冻结 affine 变换；人工线确定物理轴与逐侧权限，实际确认
  polygon 由受保护输出边的半平面检查。源截断后的自包含与逐侧诊断一致，缺失受保护侧不能静默通过；
  不要求输出包住 TIFF 外的物理线，也不修改冻结坐标或放宽亚像素内切规则。
- `--gate report` 完整保存开发错误与危险 auto；成功退出只表示诊断完成。`--gate release` 与
  `tools/verify accuracy` 要求当前 nominal 全部安全自动批准、全部角色危险 auto 为 0。
  Challenge 的安全 auto 与安全 Review 分开记录，继续争取安全自动覆盖。
- 当前开发版本尚未达到发布标准。最新样片分布和精确 receipt 见项目记忆；旧检查点的性能、黄金和平台
  结果不替代当前 release commit 的验证。
- `tools/verify` 是 Hook、CI、本地与平台脚本的唯一验证入口。Full/pre-push 先核对与 CI 相同的依赖合同，
  再运行工程测试。工程、黄金准确性、正式性能和平台资格分别报告。
- 正式 24-source 完整用户路径平均耗时必须不超过 5 秒，3 秒是持续优化目标。默认单任务运行，内部数值
  线程固定为 1；不以增加并发掩盖单 source 工作量。
- Apple Silicon macOS、Intel macOS、Windows x64 与其余发布证据必须绑定同一最终 commit；条件未齐前
  不创建 RC、tag、GitHub Release 或公开 ZIP。发布包由唯一 manifest 拥有，不包含开发源码、工具、测试和内部文档。
- 当前没有 sealed cohort，黄金未覆盖 `xpan`、`120-645`、`135-dual`；披露为尚无独立未见或真实样片
  覆盖，不冒充已验证，也不以格式白名单或禁用规则替代统一能力。

## V4.9（架构实验，不发布）

V4.9 建立 fixed-format template-first、source geometry、两级 Gate 与 source-coordinate safety，但没有
完成黄金 accuracy。它只存在于 Git history，不维护兼容路径。

## v4.2.8（当前稳定发布）

v4.2.8 证明“先看整条片带，再在理论位置附近找 outer 和 separator”可以快速覆盖规则片条。V5 继承并
重建理论 pitch、material band、native gap edge、outer/cross、有界局部搜索、缺边投影、deskew、
候选无关复用与 TIFF readback；不恢复未经校准的 confidence/best-score 终判、Grid 自证和事后裁切修补。
普通用户继续使用 [v4.2.8 Release](https://github.com/rrriiicccooo/X5-Crop/releases/tag/v4.2.8) 及包内手册。

## 回滚

恢复历史版本必须整体使用同一 commit 的 detector、configuration、schema、tests 与文档，不能跨版本拼接组件。
