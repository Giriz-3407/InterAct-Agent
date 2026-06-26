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
APP_NAME = "InterAct Desktop Agent"
COMPANY = "InterAct"

VERSION = "1.0.6"
AGENT_VERSION = VERSION

PROTOCOL_VERSION = 1

CAPABILITIES = [
    "cursor_presence",
    "annotations",
    "spotlight",
]
