"""
test_client.py — InterAct Desktop Agent, Phase 3 test client.

Connects to the local WebSocket server and drives the overlay with
synthetic cursor events. Use this to validate Phase 3 without an
InterAct backend.

Usage:
    # Demo mode — moves one cursor around the screen with periodic ripples
    python test_client.py

    # Multi-cursor demo — two cursors moving simultaneously
    python test_client.py --multi

    # Remove cursor after 5 seconds of movement
    python test_client.py --remove

Arguments:
    --host  HOST   WebSocket host (default: localhost)
    --port  PORT   WebSocket port (default: 8765)
    --multi        Launch two cursors simultaneously
    --remove       Remove test-cursor-1 after 5 seconds then keep moving test-cursor-2
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from typing import Any


WS_URI_TEMPLATE = "ws://{host}:{port}"
FPS = 60
FRAME_DELAY = 1.0 / FPS


# ---------------------------------------------------------------------------
# Message builders
# ---------------------------------------------------------------------------

def cursor_move(pid: str, x: int, y: int, color: str, name: str) -> str:
    return json.dumps({
        "event":         "cursor_move",
        "participantId": pid,
        "name":          name,
        "color":         color,
        "x":             x,
        "y":             y,
    })


def cursor_click(pid: str, x: int, y: int, color: str) -> str:
    return json.dumps({
        "event":         "cursor_click",
        "participantId": pid,
        "color":         color,
        "x":             x,
        "y":             y,
    })


def cursor_remove(pid: str) -> str:
    return json.dumps({
        "event":         "cursor_remove",
        "participantId": pid,
    })


# ---------------------------------------------------------------------------
# Cursor simulator
# ---------------------------------------------------------------------------

class CursorSimulator:
    """
    Simulates a single remote participant cursor that bounces around
    the screen and periodically emits click ripples.
    """

    def __init__(
        self,
        participant_id: str,
        name: str,
        color: str,
        start_x: float = 500.0,
        start_y: float = 300.0,
        dx: float = 5.0,
        dy: float = 3.0,
        screen_w: int = 1536,
        screen_h: int = 864,
        margin: int = 40,
        ripple_every_n_frames: int = 120,   # every 2 seconds at 60 FPS
    ) -> None:
        self.pid   = participant_id
        self.name  = name
        self.color = color
        self.x     = start_x
        self.y     = start_y
        self.dx    = dx
        self.dy    = dy
        self.w     = screen_w
        self.h     = screen_h
        self.margin = margin
        self.ripple_every = ripple_every_n_frames
        self.frame = 0

    def step(self) -> list[str]:
        """Advance one frame. Returns list of JSON messages to send."""
        messages: list[str] = []

        self.x += self.dx
        self.y += self.dy

        if self.x < self.margin or self.x > self.w - self.margin:
            self.dx = -self.dx
            self.x = max(self.margin, min(self.x, self.w - self.margin))

        if self.y < self.margin or self.y > self.h - self.margin:
            self.dy = -self.dy
            self.y = max(self.margin, min(self.y, self.h - self.margin))

        messages.append(cursor_move(
            self.pid, int(self.x), int(self.y), self.color, self.name
        ))

        self.frame += 1
        if self.frame % self.ripple_every == 0:
            messages.append(cursor_click(
                self.pid, int(self.x), int(self.y), self.color
            ))
            print(
                f"[TestClient] click ripple @ {self.pid!r} at ({int(self.x)}, {int(self.y)})",
                flush=True,
            )

        return messages


# ---------------------------------------------------------------------------
# Demo runners
# ---------------------------------------------------------------------------

async def run_single_cursor(ws, remove_after: int = 0) -> None:
    """
    Single cursor demo. Moves test-cursor-1 around the screen.
    If remove_after > 0, removes the cursor after that many frames
    then creates test-cursor-2 to continue the demo.
    """
    sim = CursorSimulator(
        participant_id="test-cursor-1",
        name="Test User 1",
        color="#ff2222",
        dx=5.0, dy=3.0,
    )
    removed = False

    while True:
        msgs = sim.step()
        for m in msgs:
            await ws.send(m)

        # Optional: remove cursor after N frames to test cursor_remove
        if remove_after > 0 and sim.frame == remove_after and not removed:
            print(f"[TestClient] Sending cursor_remove for {sim.pid!r}", flush=True)
            await ws.send(cursor_remove(sim.pid))
            removed = True
            # Start a second cursor to confirm multi-cursor still works
            sim2 = CursorSimulator(
                participant_id="test-cursor-2",
                name="Test User 2",
                color="#22aaff",
                start_x=900.0, start_y=500.0,
                dx=-4.0, dy=4.5,
            )
            # Graft sim2 for the rest of the loop
            sim = sim2
            removed = False
            remove_after = 0

        await asyncio.sleep(FRAME_DELAY)


async def run_multi_cursor(ws) -> None:
    """
    Two cursors moving simultaneously, both sending to the same server.
    Demonstrates multi-participant support.
    """
    sim1 = CursorSimulator(
        participant_id="test-cursor-1",
        name="Alice",
        color="#ff2222",
        start_x=300.0, start_y=200.0,
        dx=5.0, dy=3.5,
    )
    sim2 = CursorSimulator(
        participant_id="test-cursor-2",
        name="Bob",
        color="#22aaff",
        start_x=900.0, start_y=600.0,
        dx=-4.5, dy=3.0,
        ripple_every_n_frames=90,   # ripple slightly out of phase
    )

    while True:
        for m in sim1.step():
            await ws.send(m)
        for m in sim2.step():
            await ws.send(m)
        await asyncio.sleep(FRAME_DELAY)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main(args: argparse.Namespace) -> None:
    uri = WS_URI_TEMPLATE.format(host=args.host, port=args.port)
    print(f"[TestClient] Connecting to {uri} …", flush=True)

    try:
        import websockets
        async with websockets.connect(uri) as ws:
            print(f"[TestClient] Connected. Mode: {'multi' if args.multi else 'single'}", flush=True)
            if args.multi:
                await run_multi_cursor(ws)
            elif args.remove:
                # Remove cursor-1 after 5 seconds (300 frames at 60 FPS)
                await run_single_cursor(ws, remove_after=300)
            else:
                await run_single_cursor(ws)
    except OSError as exc:
        print(
            f"[TestClient] Cannot connect to {uri}: {exc}\n"
            "  Is the agent running? Start it with: python main.py",
            flush=True,
        )
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n[TestClient] Interrupted — exiting.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="InterAct Desktop Agent — Phase 3 test client"
    )
    parser.add_argument("--host",   default="localhost", help="WebSocket host (default: localhost)")
    parser.add_argument("--port",   default=8765, type=int, help="WebSocket port (default: 8765)")
    parser.add_argument("--multi",  action="store_true", help="Run two cursors simultaneously")
    parser.add_argument("--remove", action="store_true", help="Remove first cursor after 5s, spawn second")
    args = parser.parse_args()

    asyncio.run(main(args))
