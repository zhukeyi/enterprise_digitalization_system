"""Desktop Client state models — configuration and runtime state (M2-T4).

Defines the data contracts between the Tauri frontend and the FDE backend.
These models are the canonical interface for the desktop AI assistant.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ══════════════════════════════════════════════════════════════════
# Hotkey Configuration
# ══════════════════════════════════════════════════════════════════


class HotkeyModifier(StrEnum):
    """Supported modifier keys."""

    CTRL = "ctrl"
    ALT = "alt"
    SHIFT = "shift"
    META = "meta"  # Cmd on macOS, Win on Windows


class HotkeyConfig(BaseModel):
    """Configurable global hotkey for invoking the AI assistant."""

    modifiers: list[HotkeyModifier] = Field(
        default_factory=lambda: [HotkeyModifier.CTRL, HotkeyModifier.SHIFT],
        min_length=1,
        max_length=3,
        description="Modifier key combination",
    )
    key: str = Field(default="Space", min_length=1, max_length=32, description="Main key")
    enabled: bool = Field(default=True)
    conflicts_with: list[str] = Field(
        default_factory=list, description="Known conflicting system shortcuts"
    )

    @property
    def display_string(self) -> str:
        """Human-readable shortcut string (e.g., Ctrl+Shift+Space)."""
        if self.is_empty:
            return "(disabled)"
        parts = [m.value.capitalize() for m in self.modifiers] + [self.key]
        return "+".join(parts)

    @property
    def is_empty(self) -> bool:
        """Check if the hotkey is effectively disabled."""
        return not self.modifiers or not self.key

    def conflicts(self, other: HotkeyConfig) -> bool:
        """Check if this hotkey conflicts with another."""
        return set(self.modifiers) == set(other.modifiers) and self.key.lower() == other.key.lower()


# ══════════════════════════════════════════════════════════════════
# Window & Tray State
# ══════════════════════════════════════════════════════════════════


class WindowPosition(BaseModel):
    """Desktop window position and size."""

    x: int = Field(default=100)
    y: int = Field(default=100)
    width: int = Field(default=480, ge=320, le=3840)
    height: int = Field(default=640, ge=240, le=2160)


class WindowState(BaseModel):
    """Runtime state of the desktop assistant window."""

    visible: bool = Field(default=False)
    position: WindowPosition = Field(default_factory=WindowPosition)
    always_on_top: bool = Field(default=True)
    opacity: float = Field(default=0.95, ge=0.3, le=1.0)

    def toggle_visibility(self) -> bool:
        """Toggle window visibility and return the new state."""
        self.visible = not self.visible
        return self.visible


class TrayState(BaseModel):
    """System tray icon state."""

    visible: bool = Field(default=True)
    show_notifications: bool = Field(default=True)
    unread_count: int = Field(default=0, ge=0)
    last_notification: str = Field(default="")


# ══════════════════════════════════════════════════════════════════
# Clipboard Context
# ══════════════════════════════════════════════════════════════════


class CaptureSource(StrEnum):
    """How the text was captured."""

    SELECTION = "selection"  # User highlighted text
    CLIPBOARD = "clipboard"  # System clipboard content
    ACTIVE_WINDOW = "active_window"  # Text from the active input field


class CapturedText(BaseModel):
    """Text captured from the user's desktop context."""

    text: str = Field(max_length=10000, description="Captured text content")
    source: CaptureSource = Field(default=CaptureSource.SELECTION)
    app_name: str = Field(default="", description="Source application name")
    app_bundle_id: str = Field(default="", description="macOS bundle ID or Windows exe path")
    selection_length: int = Field(default=0, ge=0)
    captured_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )

    @property
    def is_empty(self) -> bool:
        return len(self.text.strip()) == 0

    def truncate(self, max_chars: int = 2000) -> CapturedText:
        """Return a truncated copy for API transmission."""
        return self.model_copy(update={"text": self.text[:max_chars]})


class FillMode(StrEnum):
    """How to insert the AI response into the desktop app."""

    CLIPBOARD = "clipboard"
    PASTE = "paste"
    TYPE = "type"


class FillTarget(BaseModel):
    """Where to paste/insert the AI response."""

    mode: FillMode = Field(default=FillMode.CLIPBOARD, description="Insertion method")
    delay_ms: int = Field(default=50, ge=0, le=500, description="Delay before fill operation")
    restore_clipboard: bool = Field(
        default=True, description="Restore original clipboard content after fill"
    )


# ══════════════════════════════════════════════════════════════════
# Desktop AI Request/Response
# ══════════════════════════════════════════════════════════════════


class AIMode(StrEnum):
    """AI interaction modes for the desktop assistant."""

    CHAT = "chat"
    TRANSLATE = "translate"
    SUMMARIZE = "summarize"
    EXPLAIN = "explain"


class DesktopAIRequest(BaseModel):
    """Request from desktop client to FDE backend."""

    query: str = Field(min_length=1, max_length=10000, description="User query text")
    context: CapturedText | None = Field(default=None, description="Captured desktop context")
    session_id: str | None = Field(default=None, description="Continuation session ID")
    mode: AIMode = Field(default=AIMode.CHAT, description="AI interaction mode")
    stream: bool = Field(default=True, description="Use streaming response")


class DesktopAIResponse(BaseModel):
    """Response from FDE backend to desktop client."""

    text: str = Field(default="", description="AI response text")
    session_id: str = Field(default="")
    mode: AIMode = Field(default=AIMode.CHAT)
    worker_outputs: dict[str, Any] = Field(
        default_factory=dict, description="Aggregated worker results"
    )
    conflicts_detected: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    error: str | None = Field(default=None)


class ThemeMode(StrEnum):
    """Desktop app visual themes."""

    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


class DesktopClientConfig(BaseModel):
    """Persisted desktop client configuration."""

    hotkey: HotkeyConfig = Field(default_factory=HotkeyConfig)
    window: WindowState = Field(default_factory=WindowState)
    tray: TrayState = Field(default_factory=TrayState)
    fill_target: FillTarget = Field(default_factory=FillTarget)
    backend_url: str = Field(default="http://localhost:8000")
    theme: ThemeMode = Field(default=ThemeMode.SYSTEM)
    language: str = Field(default="zh-CN")
    auto_start: bool = Field(default=True)
    max_context_chars: int = Field(default=2000, ge=100, le=10000)
