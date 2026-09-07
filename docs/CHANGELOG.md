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
- Deskew 仅整理已批准结果，不参与 placement 或黄金判定。正式 TIFF 保持 16-bit RGB、ICC、resolution、
  支持的 metadata 与无损压缩，写入 Orientation=1；整组 staging 完成后原子发布到新目录。

### 报告与验证

- Normal report 与 Debug Analysis 只显示同次检测事实，分开 proposal、candidate、正式输出、runner、
  typed failure、calibration identity 和实际工作量，不重新检测或求解。当前 Report revision 为
  `x5crop_v5_template_report_68`，不保留旧 schema 兼容层。
- 每条 lane 保留已有 best 与单个 runner 的完整 proposal 或 typed unavailable；每份由同一输出 owner
  物化一次，正式输出复用 primary。新增投影次数与逐 slot 输出评估次数，不扩大候选搜索或自动权限。
- Development gold 分开比较 proposal、candidate 与 approved output。Runtime 的实际数值预算评估和
  CandidateGate 的预算阻断分开统计；未评估不能冒充通过。比例 H 的预算诊断只记录实际消费和阻断事实。
  每份保留候选独立记录最终 footprint 与方向性黄金标签，允许多份同时安全；无法生成不算不安全负例。
  集合统计区分单份安全、多份安全、全部保留候选不安全和存在未能评价的候选。Gold record / summary 为 v19 / v22。
- 人工 reference 只来自原图坐标中的用户确认或独立外部测量，绑定 source SHA；模型与自动工具只产生
  proposal。Comparator 对原图黄金执行一次冻结 affine 变换，源截断 polygon 使用人工边界半平面判断。
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
