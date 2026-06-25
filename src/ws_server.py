"""
ws_server.py — InterAct Desktop Agent, RC1

Local WebSocket server that receives cursor events from external clients
and bridges them safely to the Qt overlay on the main thread.

Threading model:
  - Main thread    : Qt event loop (overlay, painting, timers)
  - Daemon thread  : asyncio event loop (WebSocket server)
  - Bridge         : CursorBridge(QObject) with Qt Signals

  CursorBridge signals are emitted from the asyncio/daemon thread.
  PySide6 automatically queues cross-thread signal emissions, so the
  connected overlay slots execute on the Qt main thread with no explicit
  locking required.

Supported events (JSON over WebSocket):
  cursor_move   — move/create a participant cursor
  cursor_click  — add a click ripple at a position
  cursor_remove — remove a participant cursor
  annotation_update — update/create a screen annotation
  annotation_clear  — clear all annotations for a participant
  spotlight_update  — toggle spotlight effect

On connect, the server immediately sends an agent_info handshake message
so the browser can validate protocol compatibility.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any

import websockets
import websockets.exceptions

from PySide6.QtCore import QObject, Signal

from src.agent_version import AGENT_VERSION, PROTOCOL_VERSION, CAPABILITIES

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Qt signal bridge — emitted from asyncio thread, delivered on Qt thread
# ---------------------------------------------------------------------------

class CursorBridge(QObject):
    """
    Qt signal hub connecting the asyncio WebSocket server to the Qt overlay.

    All signals are emitted from the asyncio daemon thread. PySide6 detects
    the cross-thread emission and automatically delivers the signal via a
    queued connection, meaning the connected slots execute safely on the
    Qt main thread.

    Signals:
        cursor_moved(participant_id, x, y, color, name)
            Maps to overlay.set_cursor_position(...)

        cursor_clicked(participant_id, x, y, color)
            Maps to overlay.add_click_ripple(...)

        cursor_removed(participant_id)
            Maps to overlay.remove_cursor(...)

        annotation_updated(participant_id, annotation_id, type,
                           startX, startY, endX, endY, color, name)
            Maps to overlay.set_annotation(...)

        annotation_cleared(participant_id)
            Maps to overlay.clear_annotations(...)

        spotlight_updated(participant_id, active)
            Maps to overlay.set_spotlight(...)

        client_disconnected()
            Notifies the overlay that all clients have left.
    """

    cursor_moved        = Signal(str, int, int, str, str)   # id, x, y, color, name
    cursor_clicked      = Signal(str, int, int, str)         # id, x, y, color
    cursor_removed      = Signal(str)                         # id
    annotation_updated  = Signal(str, str, str, float, float, float, float, str, str)
    annotation_cleared  = Signal(str)                         # participant_id
    spotlight_updated   = Signal(str, bool)                   # participant_id, active
    client_disconnected = Signal()
    server_started      = Signal()


# ---------------------------------------------------------------------------
# Handshake helpers
# ---------------------------------------------------------------------------

def _build_agent_info(host: str, port: int) -> dict:
    """
    Build the agent_info handshake payload sent immediately on connect.

    Schema (must match BROWSER_PROTOCOL_VERSION in desktopAgent.ts):
      event            : "agent_info"
      version          : human-readable semver string
      protocol_version : integer — must match browser's BROWSER_PROTOCOL_VERSION
      capabilities     : list of feature flag strings
      platform         : OS identifier
      agent_port       : the port this server is actually listening on
    """
    import platform as _platform
    return {
        "event":            "agent_info",
        "version":          AGENT_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "capabilities":     CAPABILITIES,
        "platform":         _platform.system().lower(),   # e.g. "windows"
        "agent_port":       port,
    }


# ---------------------------------------------------------------------------
# WebSocket protocol handler
# ---------------------------------------------------------------------------

def _make_handler(bridge: CursorBridge, host: str, port: int):
    """
    Returns an async WebSocket connection handler closed over `bridge`.
    Using a closure avoids module-level globals.
    """
    handshake_payload = json.dumps(_build_agent_info(host, port))

    async def _handle_client(websocket) -> None:
        addr = websocket.remote_address
        log.info("Client connected: %s", addr)

        # ── Send agent_info handshake immediately ─────────────────────────
        try:
            await websocket.send(handshake_payload)
            log.info(
                "Handshake sent to %s: version=%s protocol=%d capabilities=%s",
                addr,
                AGENT_VERSION,
                PROTOCOL_VERSION,
                CAPABILITIES,
            )
        except Exception as exc:  # noqa: BLE001
            log.error("Failed to send handshake to %s: %s", addr, exc)
            return

        # ── Message receive loop ──────────────────────────────────────────
        try:
            async for raw_message in websocket:
                _dispatch(bridge, raw_message, addr)

        except websockets.exceptions.ConnectionClosedOK:
            pass  # clean client-initiated disconnect
        except websockets.exceptions.ConnectionClosedError as exc:
            log.warning("Client %s disconnected with error: %s", addr, exc)
        except Exception as exc:  # noqa: BLE001
            log.error("Unexpected error from %s: %s", addr, exc)
        finally:
            log.info("Client disconnected: %s", addr)
            bridge.client_disconnected.emit()

    return _handle_client


def _dispatch(bridge: CursorBridge, raw: str, addr: Any) -> None:
    """
    Parse one raw WebSocket message and emit the appropriate bridge signal.
    Invalid or unknown messages are logged and silently dropped — they never
    raise or crash the agent.
    """
    # ── Parse JSON ────────────────────────────────────────────────────────
    try:
        msg: dict = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        log.warning("Invalid JSON from %s: %r", addr, raw)
        return

    if not isinstance(msg, dict):
        log.warning("Expected JSON object, got %r from %s", type(msg).__name__, addr)
        return

    event = msg.get("event")

    # ── cursor_move ───────────────────────────────────────────────────────
    if event == "cursor_move":
        try:
            pid   = str(msg["participantId"])
            x     = int(msg["x"])
            y     = int(msg["y"])
            color = str(msg.get("color", "#ff2222"))
            name  = str(msg.get("name", "Unknown"))
        except (KeyError, TypeError, ValueError) as exc:
            log.warning("Malformed cursor_move from %s: %s", addr, exc)
            return
        # DEBUG — this fires at ~20 fps per participant; keep out of INFO
        log.debug("cursor_move: %r @ (%d, %d)", pid, x, y)
        bridge.cursor_moved.emit(pid, x, y, color, name)

    # ── cursor_click ──────────────────────────────────────────────────────
    elif event == "cursor_click":
        try:
            pid   = str(msg["participantId"])
            x     = int(msg["x"])
            y     = int(msg["y"])
            color = str(msg.get("color", "#ff2222"))
        except (KeyError, TypeError, ValueError) as exc:
            log.warning("Malformed cursor_click from %s: %s", addr, exc)
            return
        log.info("cursor_click: %r @ (%d, %d)", pid, x, y)
        bridge.cursor_clicked.emit(pid, x, y, color)

    # ── cursor_remove ─────────────────────────────────────────────────────
    elif event == "cursor_remove":
        try:
            pid = str(msg["participantId"])
        except (KeyError, TypeError) as exc:
            log.warning("Malformed cursor_remove from %s: %s", addr, exc)
            return
        log.info("cursor_remove: %r", pid)
        bridge.cursor_removed.emit(pid)

    # ── annotation_update ─────────────────────────────────────────────────
    elif event == "annotation_update":
        try:
            pid      = str(msg["participantId"])
            annot_id = str(msg["annotationId"])
            atype    = str(msg["type"])
            sx       = float(msg["startX"])
            sy       = float(msg["startY"])
            ex       = float(msg["endX"])
            ey       = float(msg["endY"])
            color    = str(msg.get("color", "#ff2222"))
            name     = str(msg.get("name", "Unknown"))
        except (KeyError, TypeError, ValueError) as exc:
            log.warning("Malformed annotation_update from %s: %s", addr, exc)
            return
        log.debug("annotation_update: %r id=%r type=%s", pid, annot_id, atype)
        bridge.annotation_updated.emit(pid, annot_id, atype, sx, sy, ex, ey, color, name)

    # ── annotation_clear ──────────────────────────────────────────────────
    elif event == "annotation_clear":
        try:
            pid = str(msg["participantId"])
        except (KeyError, TypeError) as exc:
            log.warning("Malformed annotation_clear from %s: %s", addr, exc)
            return
        log.info("annotation_clear: %r", pid)
        bridge.annotation_cleared.emit(pid)

    # ── spotlight_update ──────────────────────────────────────────────────
    elif event == "spotlight_update":
        try:
            pid    = str(msg["participantId"])
            active = bool(msg["active"])
        except (KeyError, TypeError) as exc:
            log.warning("Malformed spotlight_update from %s: %s", addr, exc)
            return
        log.info("spotlight_update: %r active=%s", pid, active)
        bridge.spotlight_updated.emit(pid, active)

    # ── Unknown event ─────────────────────────────────────────────────────
    else:
        log.warning("Unknown event ignored: %r from %s", event, addr)


# ---------------------------------------------------------------------------
# asyncio server entrypoint
# ---------------------------------------------------------------------------

async def _server_main(bridge: CursorBridge, host: str, port: int) -> None:
    handler = _make_handler(bridge, host, port)
    async with websockets.serve(handler, host, port):
        log.info("WebSocket server listening on ws://%s:%d", host, port)
        bridge.server_started.emit()
        await asyncio.Future()   # run forever until the daemon thread is killed


# ---------------------------------------------------------------------------
# Public: launch server on a daemon thread
# ---------------------------------------------------------------------------

def start_websocket_server(
    bridge: CursorBridge,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> threading.Thread:
    """
    Start the WebSocket server on a background daemon thread.

    The thread is daemonized so it exits automatically when the Qt main
    thread (and therefore the process) exits — no manual cleanup required.

    Args:
        bridge: The CursorBridge whose signals will be emitted on events.
        host:   Bind address (default: "127.0.0.1").
        port:   TCP port (default: 8765).

    Returns:
        The started Thread object (rarely needed by callers).
    """
    def _thread_target() -> None:
        asyncio.run(_server_main(bridge, host, port))

    thread = threading.Thread(
        target=_thread_target,
        name="ws-server",
        daemon=True,          # exits when main Qt thread exits
    )
    thread.start()
    return thread
