"""MapAgent WebSocket — real-time analysis push (M3-T11).

Provides WebSocket endpoints for:
1. Real-time analysis progress updates
2. Pushing analysis results to connected clients
3. Connection management with session tracking

Usage (in FastAPI app):
    from agents.map_agent.websocket import ws_router
    app.include_router(ws_router)

Client connects:
    ws://host/map/ws/analysis/{session_id}

Server pushes messages:
    {"type": "progress", "stage": "fetch_entities", "progress": 33}
    {"type": "result", "data": {...}}
    {"type": "error", "message": "..."}
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("fde.map.websocket")

__all__ = ["ConnectionManager", "get_manager", "ws_router"]

# ══════════════════════════════════════════════════════════════════
# Connection Manager
# ══════════════════════════════════════════════════════════════════


class ConnectionManager:
    """Manages WebSocket connections grouped by session ID.

    Supports multiple clients per session (e.g., user opens
    multiple browser tabs).
    """

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        """Accept a new WebSocket connection and register it."""
        await websocket.accept()
        if session_id not in self._connections:
            self._connections[session_id] = []
        self._connections[session_id].append(websocket)
        logger.info(
            "WebSocket connected: session=%s (total: %d)", session_id, self.count(session_id)
        )

    def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        if session_id in self._connections:
            if websocket in self._connections[session_id]:
                self._connections[session_id].remove(websocket)
            if not self._connections[session_id]:
                del self._connections[session_id]
        logger.info("WebSocket disconnected: session=%s", session_id)

    async def broadcast(self, session_id: str, message: dict[str, Any]) -> None:
        """Broadcast a message to all connections in a session."""
        if session_id not in self._connections:
            return

        text = json.dumps(message, ensure_ascii=False, default=str)
        disconnected: list[WebSocket] = []

        for ws in self._connections[session_id]:
            try:
                await ws.send_text(text)
            except Exception as e:
                logger.warning("Failed to send to WebSocket: %s", e)
                disconnected.append(ws)

        for ws in disconnected:
            self.disconnect(session_id, ws)

    async def send_progress(
        self,
        session_id: str,
        stage: str,
        progress: int,
        detail: str = "",
    ) -> None:
        """Send a progress update message."""
        await self.broadcast(
            session_id,
            {
                "type": "progress",
                "stage": stage,
                "progress": progress,
                "detail": detail,
            },
        )

    async def send_result(self, session_id: str, data: dict[str, Any]) -> None:
        """Send a final analysis result message."""
        await self.broadcast(
            session_id,
            {
                "type": "result",
                "data": data,
            },
        )

    async def send_error(self, session_id: str, message: str) -> None:
        """Send an error message."""
        await self.broadcast(
            session_id,
            {
                "type": "error",
                "message": message,
            },
        )

    def count(self, session_id: str | None = None) -> int:
        """Count active connections (total or per session)."""
        if session_id is None:
            return sum(len(conns) for conns in self._connections.values())
        return len(self._connections.get(session_id, []))

    def get_active_sessions(self) -> list[str]:
        """Return list of session IDs with active connections."""
        return list(self._connections.keys())


# Singleton
_manager: ConnectionManager | None = None


def get_manager() -> ConnectionManager:
    """Get the singleton ConnectionManager instance."""
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager


# ══════════════════════════════════════════════════════════════════
# WebSocket Router
# ══════════════════════════════════════════════════════════════════

ws_router = APIRouter(prefix="/map/ws", tags=["map-websocket"])


@ws_router.websocket("/analysis/{session_id}")
async def ws_analysis(websocket: WebSocket, session_id: str) -> None:
    """WebSocket endpoint for real-time analysis updates.

    Client connects to receive:
    - Progress updates during analysis pipeline
    - Final analysis results
    - Error messages

    Client can also send messages:
    - {"action": "ping"} — server responds with {"type": "pong"}
    - {"action": "status"} — server responds with connection status
    """
    manager = get_manager()
    await manager.connect(session_id, websocket)

    try:
        # Send welcome message
        await websocket.send_text(
            json.dumps(
                {
                    "type": "connected",
                    "session_id": session_id,
                    "message": "WebSocket 已连接，等待分析任务...",
                },
                ensure_ascii=False,
            )
        )

        # Listen for client messages
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
                msg = json.loads(raw)

                if msg.get("action") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                elif msg.get("action") == "status":
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "status",
                                "session_id": session_id,
                                "connections": manager.count(session_id),
                                "active_sessions": manager.get_active_sessions(),
                            }
                        )
                    )
                else:
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "info",
                                "message": f"未知 action: {msg.get('action', 'N/A')}",
                            }
                        )
                    )

            except TimeoutError:
                # No message for 60s — send keepalive
                await websocket.send_text(json.dumps({"type": "keepalive"}))
            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "error",
                            "message": "无效的 JSON 消息",
                        }
                    )
                )

    except WebSocketDisconnect:
        manager.disconnect(session_id, websocket)
        logger.info("Client disconnected: session=%s", session_id)
    except Exception as e:
        logger.error("WebSocket error: %s", e)
        manager.disconnect(session_id, websocket)
