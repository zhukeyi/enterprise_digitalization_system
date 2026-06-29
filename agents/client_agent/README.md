# Client Agent — 桌面AI助手

## 职责
- Tauri 客户端框架（系统托盘 + 主窗口 UI）
- 全局快捷键（Ctrl+Shift+Space 可配置）
- 文本捕获（Windows API / macOS AppleScript）
- AI 接口调用 + 结果回填（自动粘贴/剪贴板）

## 技术栈
- Tauri 2.x（Rust 后端 + 前端 WebView）
- macOS / Windows 双平台支持

## M2 任务
| 任务 | 说明 | 状态 |
|:---|:---|:---|
| M2-T10 | 客户端框架搭建 | 待开发 |
| M2-T11 | 全局快捷键 | 待开发 |
| M2-T12 | 文本捕获 | 待开发 |
| M2-T13 | AI 调用 + 回填 | 待开发 |

## 依赖
- Rust toolchain + Node.js 20+
- 平台 API（Windows: win32 API; macOS: Accessibility）
