# X5 Crop

[V5 中文开发预览手册](docs/user-guide.zh-CN.md) ·
[V5 English Preview Guide](docs/user-guide.en.md) ·
[V5 中文快速启动](docs/quick-start.zh-CN.md) ·
[V5 English Quick Start](docs/quick-start.en.md)

X5 Crop 用于裁切 Hasselblad / Imacon X5 片夹扫描 TIFF。用户提供胶片格式，并确认默认或明确的
照片格数；程序先按已知格式放置固定模板，再从整条片带到局部边界逐步对准。只有照片内容、输出
范围和 TIFF 写出都安全时才输出整组照片，否则保留原扫描件供人工检查。

X5 Crop crops Hasselblad / Imacon X5 holder-scan TIFFs. You provide the film
format and confirm either the default or an explicit exposure-slot count. The
program aligns a fixed template from the whole strip down to local boundaries,
then writes the complete set only when content, output bounds, and TIFF
fidelity are safe.

本仓库 `main` 是尚未发布的 V5 开发源码，上述链接描述 V5。当前公开稳定版仍是
**v4.2.8**；普通用户应以 Release 包内随附的 v4.2.8 手册为准。

This repository's `main` branch is the unreleased V5 development source, and
the links above describe V5. The latest public stable release remains
**v4.2.8**; regular users should follow the v4.2.8 documentation bundled in
that release.

发布包 / Release package: download `X5-Crop-vX.X.zip` from
[GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases), not the
generated Source code archive.

维护文档：[当前架构](docs/ARCHITECTURE.md) · [更新日志](docs/CHANGELOG.md)

License: MIT — [LICENSE](LICENSE)
