# M2-T4 Tauri 构建 TODO

以下任务需要特定开发环境（Rust toolchain / Node.js / 平台 SDK），无法在当前 Python 环境中完成。

## 环境要求
- Rust toolchain (rustup, cargo)
- Node.js 20+
- Tauri CLI 2.x (`cargo install tauri-cli`)
- macOS: Xcode Command Line Tools + Accessibility 权限
- Windows: MSVC Build Tools + Windows SDK

## TODO List

### T-1: Tauri 项目骨架搭建 (4h)
- [ ] `npm create tauri-app@latest` 初始化项目
- [ ] 配置 `tauri.conf.json`（窗口大小480×640, alwaysOnTop=true, 系统托盘）
- [ ] 配置 `Cargo.toml`（依赖: tauri, tauri-plugin-shell, tauri-plugin-global-shortcut）
- [ ] 前端 WebView: Vue 3 + Vite
- [ ] 项目结构:
  ```
  agents/client_agent/
    src-tauri/         # Rust 后端
    src/               # Vue.js 前端
    src-py/            # Python SDK（已完成）
  ```

### T-2: macOS 版本构建 (8h)
- [ ] 全局快捷键注册（macOS CGEvent / Tauri global-shortcut plugin）
- [ ] 文本捕获实现（Accessibility API: AXUIElementCopyAttributeValue）
- [ ] AI 回填实现（NSPasteboard + CGEventPost 模拟 Cmd+V）
- [ ] 打包脚本: `npm run tauri build -- --target universal-apple-darwin`
- [ ] 产物: `FDE_AI_Assistant.dmg`

### T-3: Windows 版本构建 (6h)
- [ ] 全局快捷键注册（Win32 RegisterHotKey API / Tauri plugin）
- [ ] 文本捕获实现（UI Automation: IUIAutomationTextPattern）
- [ ] AI 回填实现（SendInput 模拟 Ctrl+V）
- [ ] 打包脚本: `npm run tauri build -- --target x86_64-pc-windows-msvc`
- [ ] 产物: `FDE_AI_Assistant.exe` / `FDE_AI_Assistant.msi`

### T-4: 认证流程集成 (2h)
- [ ] 接入 Python SDK 的 DesktopAuthManager
- [ ] 登录窗口 UI（用户名/密码 → 获取 JWT）
- [ ] Token 缓存（Tauri secure storage → OS keychain）
- [ ] 自动续期（调用 /auth/refresh）

### T-5: AI 接口对接 (3h)
- [ ] HTTP 请求封装（POST /v1/chat/completions，含 JWT Bearer header）
- [ ] 流式响应处理（SSE stream → 实时显示）
- [ ] 错误处理（网络异常、认证过期重试）

### T-6: CI/CD 构建流水线 (2h)
- [ ] GitHub Actions: macOS runner + Windows runner
- [ ] 自动版本号（从 git tag 读取）
- [ ] 产物上传（.dmg / .exe → Release assets）

---
**当前状态**: Python SDK 已完成（models/auth/tests）
**下一步**: 安排具有相应开发环境的工程师执行 T-1 ~ T-6