# X5 Crop

[中文用户手册](docs/user-guide.zh-CN.md) ·
[English User Guide](docs/user-guide.en.md) ·
[中文快速启动](docs/quick-start.zh-CN.md) ·
[English Quick Start](docs/quick-start.en.md)

X5 Crop 用于保守裁切 Hasselblad / Imacon X5 片夹扫描 TIFF。用户提供胶片格式与片条模式；
程序只在能够完整保护照片内容、限制多余边缘并保真写回 TIFF 时输出单张照片，否则将原扫描件
放入 `needs_review/`。仓库当前源码是唯一的 V5 current-only 实现；当前公开稳定版本仍为
**v4.2.8**，V5 尚未发布。

X5 Crop conservatively crops Hasselblad / Imacon X5 holder-scan TIFFs. You
provide the film format and strip mode. It writes individual photos only when
content protection, excess margins, and TIFF fidelity are all safe; otherwise
it places the source scan in `needs_review/`. The repository now contains one
current-only V5 implementation. The latest public stable release remains
**v4.2.8**; V5 has not been released.

请从 [GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases) 下载
`X5-Crop-vX.X.zip`，不要下载 GitHub 自动生成的 Source code。

Download `X5-Crop-vX.X.zip` from
[GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases). Do not use
GitHub's generated Source code archive.

维护文档：[当前架构](docs/ARCHITECTURE.md) · [更新日志](docs/CHANGELOG.md)

License: MIT — [LICENSE](LICENSE)
