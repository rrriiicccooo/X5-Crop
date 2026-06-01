# X5 Crop v1 Release Notes

## v1.0.0-mvp

- 项目从 X5_Split 脚本线更名为 X5 Crop App。
- 新增 PySide6 GUI。
- 核心采用 X5_Split v17 速度平衡版。
- 默认 bleed 为 10px。
- 默认 deskew auto、analysis-enhance auto。
- 新增传统 App 数据目录：Application Support / AppData、Caches、Logs。
- 新增 Windows / macOS 卸载后残余清理脚本。
- 新增 PyInstaller 打包脚本。

## Known limitations

- 预览图暂不支持直接拖动线条手动修正。
- 低置信度自动筛选队列暂未实现。
- 当前交付为源码项目，需要在目标系统上构建二进制 App。
