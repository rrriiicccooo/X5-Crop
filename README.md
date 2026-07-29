# X5 Crop

[中文用户手册](docs/user-guide.zh-CN.md) ·
[English User Guide](docs/user-guide.en.md) ·
[中文快速启动](docs/quick-start.zh-CN.md) ·
[English Quick Start](docs/quick-start.en.md)

X5 Crop 用于保守裁切 Hasselblad / Imacon X5 片夹扫描 TIFF：在用户提供 format 与
count 后，优先不切掉真实照片内容，允许适量向外多保留，不要求唯一还原真实边界。
当前 V4.9 开发版仍只生成 source-core 复核证据，尚未实现新的安全 Grid/output 合同，
因此不导出单张 frame TIFF。稳定发布仍为 **v4.2.8**。

X5 Crop conservatively crops TIFF scans from Hasselblad / Imacon X5 holders.
Given a user-supplied format and count, it prioritizes preserving real photo
content, permits modest outward over-retention, and does not require a uniquely
reconstructed physical boundary. The current V4.9 development build still emits
source-core review evidence only and has not yet implemented the new safe
Grid/output contract, so it does not export individual frame TIFFs. The stable
release remains **v4.2.8**.

请从 [GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases) 下载
`X5-Crop-vX.X.zip`，不要下载 GitHub 自动生成的 Source code。

Download `X5-Crop-vX.X.zip` from
[GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases). Do not use
GitHub's generated Source code archive.

License: MIT — [GitHub LICENSE](https://github.com/rrriiicccooo/X5-Crop/blob/main/LICENSE)
