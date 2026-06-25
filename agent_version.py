"""
agent_version.py — InterAct Desktop Agent

Single source of truth for version constants.

These values are:
  - Sent in the agent_info handshake payload on every WebSocket connection.
  - Used by the browser to validate protocol compatibility.
  - Embedded into the PyInstaller build via interact_agent.spec.

Bump rules:
  AGENT_VERSION      — any release (semver)
  PROTOCOL_VERSION   — increment ONLY when the WebSocket message schema
                       changes in a backwards-incompatible way. The browser
                       will refuse to operate with a mismatched version.
"""

# Human-readable semver release string
AGENT_VERSION: str = "1.0.0"

# Integer wire-protocol version.
# Browser-side BROWSER_PROTOCOL_VERSION must match exactly.
PROTOCOL_VERSION: int = 1

# Feature flags advertised to the browser in the agent_info handshake.
# Add entries here when new overlay capabilities are shipped.
CAPABILITIES: list[str] = [
    "cursor_presence",
    "annotations",
    "spotlight",
]
