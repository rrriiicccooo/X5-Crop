# X5 Crop 更新日志

本文件记录版本级行为与验证边界。当前合同见 [ARCHITECTURE.md](ARCHITECTURE.md)，
当前目标与风险见 [PROJECT_MEMORY.md](PROJECT_MEMORY.md)；逐次实现与实验保留在 Git history。

## V5（开发中，尚未发布）

### 检测与裁切

- 用户提供 format 并确认默认或显式 count；空白曝光格保留 ordinal，不猜格式、数量或空白。
  任一必需 slot 不安全时，整张 source 进入 `needs_review`。
- format/count 建立 source 共用的 W/H/pitch 模板，直接边缘保持原生坐标；校准 Grid、source W、
  aspect authority 与局部 Separator/Contact/Overlap 关系在各自权限内补全缺失信息。
- 整条片带与局部边界使用一次登记的有界测量。原生 16-bit 粗测保留弱材料变化，宽缓边按真实逐线
  支撑与完整物理直线域关联；不同观察身份、合法连接和保护范围完整保留，超出工作上限进入 Review。
- 每条源 TIFF 共用固定 `1.1W × 1.1H` 窗口，四边各 5% 留边包含全部基础保护。程序只选择位置，
  不叠加额外留边或小画幅固定下限。完整可见内容、倾斜角点与合法物理包络无法容纳时保留固定提案，
  不扩大窗口。共同 H 输出也必须用同一固定框保护全部获权解释。
- 只有真实 TIFF 外缘允许源边截断；内部 lane 越界不能通过缩框绕过。Deskew 是批准后的可选整理，
  不参与检测与 Gate；源边截断、旋转外包矩形和整数取整可能改变最终 TIFF 像素宽高。
- 内容保护限于 TIFF 中已记录的照片内容，不恢复片夹遮挡的画面。外侧颜色连续性和弱信号只作观测，
  不单独授予片夹身份或裁切权限。

### 诊断与黄金验证

- 完整保护包络无法放入固定窗口时，原生提案保留已拟合位置及全部保护需求，预算失败继续阻止自动
  输出。恢复 pre-local 提案后，先重评其直接角色事实再测量共同 W，原失败与备选继续保留。
- 首选无法形成完整裁切而 canonical runner 已完整时，source proposal 引用备选的原几何；报告、
  Debug 完整性摘要与黄金比较保持一致。原角色、失败、Review 决定与自动输出权限保留。
- Debug Analysis 展示实际测量、首选、备选与有条件提案、完整保护范围、来源和阻断原因，
  不生成正式照片，也不复用报告替代下一次正式检测。
- 开发黄金独立评价每份已生成 footprint，区分生成、资格与最终决定；同一 task 可以有多份安全提案。
  人工确认的可见边界严格阻断向内裁切，向外距离只作诊断，不按逐侧 5% 另设上限。
- 离线可用性排序按 source 分组，分开报告折外与样本内结果；开发分数不是校准概率，Runtime 未启用
  评分选择。人工 reference、source-SHA 绑定和评测角色不由自动工具改写。
- 序列、Cross、共同输出及最终采样保留可重放的 typed evidence 和工作量账本；报告回读复用当前
  几何 owner，不以自洽汇总代替完整物理保护检查。

### 运行与交付

- V5 只有一条 current-only production path。依赖版本由 `tools/install/dependencies.toml` 统一定义；
  安装器复用合格的全局依赖，并通过已识别的包管理器补齐或更新，来源不明时停止。
- 源码从仓库根目录使用 Python 命令启动；平台双击启动器用于发布包布局。中英文手册分别维护。
- TIFF I/O 保留 16-bit RGB、ICC、分辨率、受支持 metadata 与无损压缩，输出规范为 `Orientation=1`。
  输出先写 staging，再原子发布到全新目录；竞争、取消或失败保留已有目标并清理本次 staging。
  macOS 输出要求支持原子不覆盖操作的 APFS/HFS+ 卷，完成后可复制到 exFAT。
- `tools/verify` 统一承载工程、准确性、性能、平台与 Hook 验证；发布内容由
  `tools/release/manifest.py` 独占。发布资格必须按架构第 14 节绑定同一最终 commit，开发测试或
  安全 Review 不能替代 nominal 自动覆盖。当前 V5 未达到发布标准。

公开稳定版与历史版本见 [GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases)。
