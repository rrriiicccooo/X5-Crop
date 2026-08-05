# X5 Crop

[中文用户手册](docs/user-guide.zh-CN.md) ·
[English User Guide](docs/user-guide.en.md) ·
[中文快速启动](docs/quick-start.zh-CN.md) ·
[English Quick Start](docs/quick-start.en.md)

X5 Crop 用于保守裁切 Hasselblad / Imacon X5 片夹扫描 TIFF。用户提供胶片格式和片条模式；
程序在能够完整保留照片内容、控制多余边缘并安全写回 TIFF 时输出单张照片，否则明确标记为
`needs_review`。当前稳定发布为 **v4.2.8**。V4.9 已完成架构实验使命；V5 是下一生产目标，
尚未发布。

X5 Crop conservatively crops Hasselblad / Imacon X5 holder-scan TIFFs. You
provide the film format and strip mode. It writes individual photos only when
their content, margins, and TIFF output are safe; otherwise it reports
`needs_review`. The current stable release is **v4.2.8**. V4.9 remains an
architecture experiment; V5 is the next production target and is not released.

请从 [GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases) 下载
`X5-Crop-vX.X.zip`，不要下载 GitHub 自动生成的 Source code。

Download `X5-Crop-vX.X.zip` from
[GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases). Do not use
GitHub's generated Source code archive.

维护文档：[当前架构](docs/ARCHITECTURE.md) · [更新日志](docs/CHANGELOG.md)

License: MIT — [LICENSE](LICENSE)
