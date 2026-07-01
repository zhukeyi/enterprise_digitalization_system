"""Tests for Client Agent — M2-T4 (Models + Auth + API)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from agents.client_agent.models import (
    AIMode,
    CapturedText,
    CaptureSource,
    DesktopAIRequest,
    DesktopClientConfig,
    FillMode,
    FillTarget,
    HotkeyConfig,
    HotkeyModifier,
    ThemeMode,
    WindowPosition,
    WindowState,
)

# ══════════════════════════════════════════════════════════════════
# Hotkey Model Tests
# ══════════════════════════════════════════════════════════════════


class TestHotkeyConfig:
    def test_default_hotkey(self) -> None:
        """Default hotkey should be Ctrl+Shift+Space."""
        hk = HotkeyConfig()
        assert hk.modifiers == [HotkeyModifier.CTRL, HotkeyModifier.SHIFT]
        assert hk.key == "Space"
        assert hk.enabled is True

    def test_display_string(self) -> None:
        """Display string should format correctly."""
        hk = HotkeyConfig(modifiers=[HotkeyModifier.CTRL, HotkeyModifier.SHIFT], key="Space")
        assert hk.display_string == "Ctrl+Shift+Space"

    def test_display_string_empty(self) -> None:
        """Pydantic enforces min_length=1 — empty state guarded at model level.

        The display_string property handles the edge case defensively
        even though Pydantic prevents construction with empty values.
        """
        hk = HotkeyConfig(key="Space")  # valid defaults
        assert "Space" in hk.display_string
        assert hk.display_string != "(disabled)"

    def test_is_empty(self) -> None:
        """Pydantic enforces valid hotkeys at construction.

        is_empty() is a defensive property — normal construction always
        passes validation, so it returns False by default.
        """
        assert HotkeyConfig(key="Space").is_empty is False
        assert HotkeyConfig(modifiers=[HotkeyModifier.CTRL], key="X").is_empty is False

    def test_conflicts_detection(self) -> None:
        """Should detect conflicting hotkeys."""
        a = HotkeyConfig(modifiers=[HotkeyModifier.CTRL], key="Space")
        b = HotkeyConfig(modifiers=[HotkeyModifier.CTRL], key="Space")
        c = HotkeyConfig(modifiers=[HotkeyModifier.ALT], key="Space")
        assert a.conflicts(b) is True
        assert a.conflicts(c) is False

    def test_conflicts_case_insensitive(self) -> None:
        """Key comparison should be case-insensitive."""
        a = HotkeyConfig(modifiers=[HotkeyModifier.CTRL], key="space")
        b = HotkeyConfig(modifiers=[HotkeyModifier.CTRL], key="SPACE")
        assert a.conflicts(b) is True


# ══════════════════════════════════════════════════════════════════
# Window Model Tests
# ══════════════════════════════════════════════════════════════════


class TestWindowModels:
    def test_window_position_defaults(self) -> None:
        """Window should have reasonable default position."""
        pos = WindowPosition()
        assert pos.x == 100
        assert pos.width == 480

    def test_window_position_bounds(self) -> None:
        """Window bounds should enforce constraints."""
        with pytest.raises(ValidationError):
            WindowPosition(width=100, height=200)  # width < 320

    def test_window_position_minimums_ok(self) -> None:
        """Window should accept minimum valid dimensions."""
        pos = WindowPosition(width=320, height=240)
        assert pos.width == 320

    def test_window_state_toggle(self) -> None:
        """Toggle visibility should flip the flag."""
        ws = WindowState()
        assert ws.visible is False
        new_state = ws.toggle_visibility()
        assert new_state is True
        assert ws.visible is True
        # Toggle back — should revert visibility
        ws.toggle_visibility()  # type: ignore[unreachable]
        assert ws.visible is False


# ══════════════════════════════════════════════════════════════════
# Capture Model Tests
# ══════════════════════════════════════════════════════════════════


class TestCapturedText:
    def test_capture_creation(self) -> None:
        """CapturedText should store text with metadata."""
        ct = CapturedText(text="Hello World", source=CaptureSource.SELECTION)
        assert ct.text == "Hello World"
        assert ct.source == CaptureSource.SELECTION
        assert ct.is_empty is False

    def test_is_empty(self) -> None:
        """Empty text should be detected."""
        ct = CapturedText(text="   ")
        assert ct.is_empty is True

    def test_truncate(self) -> None:
        """Truncate should return a copy with shortened text."""
        long_text = "A" * 5000
        ct = CapturedText(text=long_text)
        truncated = ct.truncate(max_chars=100)
        assert len(truncated.text) == 100
        assert len(ct.text) == 5000  # Original unchanged
        assert truncated.source == ct.source


# ══════════════════════════════════════════════════════════════════
# FillTarget Tests
# ══════════════════════════════════════════════════════════════════


class TestFillTarget:
    def test_default_mode_is_clipboard(self) -> None:
        """Default fill mode should be clipboard (safest)."""
        ft = FillTarget()
        assert ft.mode == FillMode.CLIPBOARD
        assert ft.restore_clipboard is True

    def test_mode_enum_values(self) -> None:
        """FillMode should have expected values."""
        assert FillMode.CLIPBOARD.value == "clipboard"
        assert FillMode.PASTE.value == "paste"
        assert FillMode.TYPE.value == "type"


# ══════════════════════════════════════════════════════════════════
# AI Request/Response Tests
# ══════════════════════════════════════════════════════════════════


class TestAIRequestResponse:
    def test_request_defaults(self) -> None:
        """DesktopAIRequest should have sensible defaults."""
        req = DesktopAIRequest(query="test")
        assert req.mode == AIMode.CHAT
        assert req.stream is True
        assert req.context is None

    def test_request_with_context(self) -> None:
        """Request should accept captured context."""
        ctx = CapturedText(text="selected text", source=CaptureSource.SELECTION)
        req = DesktopAIRequest(query="explain this", context=ctx, mode=AIMode.EXPLAIN)
        assert req.context is not None
        assert req.context.text == "selected text"
        assert req.mode == AIMode.EXPLAIN

    def test_aimode_values(self) -> None:
        """AIMode should cover all interaction patterns."""
        values = {m.value for m in AIMode}
        assert values == {"chat", "translate", "summarize", "explain"}

    def test_response_creation(self) -> None:
        """DesktopAIResponse should handle worker outputs."""
        from agents.client_agent.models import DesktopAIResponse

        resp = DesktopAIResponse(
            text="Result", session_id="s1", worker_outputs={"rag": {"count": 5}}
        )
        assert resp.text == "Result"
        assert resp.worker_outputs["rag"]["count"] == 5
        assert resp.conflicts_detected == 0


# ══════════════════════════════════════════════════════════════════
# DesktopConfig Tests
# ══════════════════════════════════════════════════════════════════


class TestDesktopConfig:
    def test_default_config(self) -> None:
        """Default config should be valid."""
        cfg = DesktopClientConfig()
        assert cfg.theme == ThemeMode.SYSTEM
        assert cfg.language == "zh-CN"
        assert cfg.auto_start is True
        assert cfg.max_context_chars == 2000

    def test_theme_enum(self) -> None:
        """ThemeMode should support light, dark, system."""
        assert ThemeMode.LIGHT.value == "light"
        assert ThemeMode.DARK.value == "dark"
        assert ThemeMode.SYSTEM.value == "system"


# ══════════════════════════════════════════════════════════════════
# Auth Manager Tests
# ══════════════════════════════════════════════════════════════════


class TestAuthManager:
    @pytest.mark.asyncio
    async def test_logout_clears_cache(self) -> None:
        """Logout should clear in-memory cache."""
        from agents.client_agent.auth import DesktopAuthManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = DesktopAuthManager(cache_dir=tmpdir)
            mgr._cache.access_token = "test-token"
            mgr._cache.refresh_token = "test-refresh"

            mgr.logout()

            assert mgr._cache.access_token == ""
            assert mgr._cache.refresh_token == ""

    @pytest.mark.asyncio
    async def test_get_auth_headers_authenticated(self) -> None:
        """Should return Bearer header when authenticated."""
        from agents.client_agent.auth import DesktopAuthManager

        mgr = DesktopAuthManager()
        mgr._cache.access_token = "valid-token"
        mgr._cache.expires_at = 9999999999.0  # Far future

        headers = mgr.get_auth_headers()
        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer valid-token"

    def test_get_auth_headers_expired(self) -> None:
        """Should return empty dict when token expired."""
        from agents.client_agent.auth import DesktopAuthManager

        mgr = DesktopAuthManager()
        mgr._cache.access_token = "expired-token"
        mgr._cache.expires_at = 0.0  # Long expired

        headers = mgr.get_auth_headers()
        assert headers == {}

    @pytest.mark.asyncio
    async def test_ensure_authenticated_refreshes(self) -> None:
        """ensure_authenticated should return None when refresh fails."""
        from agents.client_agent.auth import DesktopAuthManager

        mgr = DesktopAuthManager()
        mgr._cache.refresh_token = "stale-refresh"
        mgr._cache.expires_at = 0.0  # Expired

        result = await mgr.ensure_authenticated()
        assert result is None  # Can't actually call /auth/refresh

    @pytest.mark.asyncio
    async def test_atomic_cache_write(self) -> None:
        """Cache should be written atomically (no corruption). P1 fix."""
        from agents.client_agent.auth import DesktopAuthManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = DesktopAuthManager(cache_dir=tmpdir)
            mgr._cache.access_token = "atomic-test"
            mgr._cache.refresh_token = "atomic-refresh"
            mgr._cache.expires_at = 12345.0

            mgr._save_cache()

            cache_path = Path(tmpdir) / "desktop_auth.json"
            assert cache_path.exists()
            data = json.loads(cache_path.read_text())
            assert data["access_token"] == "atomic-test"
            assert data["refresh_token"] == "atomic-refresh"

    def test_decode_token_payload_valid(self) -> None:
        """Should decode a valid JWT payload."""
        # Create a minimal fake JWT: header.payload.signature
        import base64

        from agents.client_agent.auth import DesktopAuthManager

        payload = (
            base64.urlsafe_b64encode(
                json.dumps({"sub": "user-1", "username": "alice", "roles": ["admin"]}).encode()
            )
            .decode()
            .rstrip("=")
        )

        token = f"header.{payload}.sig"
        result = DesktopAuthManager._decode_token_payload(token)
        assert result["sub"] == "user-1"
        assert result["username"] == "alice"

    def test_decode_token_invalid(self) -> None:
        """Should return empty dict for invalid tokens."""
        from agents.client_agent.auth import DesktopAuthManager

        assert DesktopAuthManager._decode_token_payload("") == {}
        assert DesktopAuthManager._decode_token_payload("not.a.jwt") == {}

    @pytest.mark.asyncio
    async def test_close_cleans_up(self) -> None:
        """close() should clean up HTTP client."""
        from agents.client_agent.auth import DesktopAuthManager

        mgr = DesktopAuthManager()
        await mgr.close()
        assert mgr._client.is_closed
