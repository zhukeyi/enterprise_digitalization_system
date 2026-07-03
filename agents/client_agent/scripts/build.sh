#!/bin/bash
# FDE AI Desktop Client — Build Script
# Builds Vue3 frontend + Tauri macOS dmg

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== FDE AI Desktop Build ==="
echo "Project: $PROJECT_DIR"

# 1. Build Vue3 frontend
echo ""
echo "[1/3] Building Vue3 frontend..."
cd "$PROJECT_DIR"
npm install --silent
npm run build

# 2. Build Tauri macOS .dmg
if command -v cargo &> /dev/null; then
    echo ""
    echo "[2/3] Building Tauri macOS app..."
    cargo tauri build --target universal-apple-darwin

    echo ""
    echo "[3/3] Creating .dmg..."
    DMG_SRC="$PROJECT_DIR/src-tauri/target/universal-apple-darwin/release/bundle/macos"
    DMG_OUT="$PROJECT_DIR/FDE_AI_Assistant.dmg"

    if [ -d "$DMG_SRC" ]; then
        hdiutil create -volname "FDE AI Assistant" \
            -srcfolder "$DMG_SRC/FDE AI Assistant.app" \
            -ov -format UDZO "$DMG_OUT"
        echo "DMG created: $DMG_OUT"
    else
        echo "Bundle not found at $DMG_SRC"
        echo "Skipping DMG creation (build may have failed)"
    fi
else
    echo ""
    echo "[SKIP] Rust/Cargo not available. Tauri build skipped."
    echo "  Install Rust: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
    echo "  Then install Tauri CLI: cargo install tauri-cli"
    echo ""
    echo "  Frontend built to: $PROJECT_DIR/out/"
fi

echo ""
echo "=== Build Complete ==="