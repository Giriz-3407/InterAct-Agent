"""
config.py — InterAct Desktop Agent Configuration Loader

Resolves the WebSocket server host and port with the following priority:

  1. Environment variable  INTERACT_AGENT_PORT  (port only)
  2. agent.cfg             [agent] host / port  (next to the EXE / script)
  3. Built-in defaults     127.0.0.1 : 8765

Usage:
    from config import AgentConfig, load_config

    cfg = load_config()
    print(cfg.host, cfg.port)   # e.g. '127.0.0.1', 8765

The config file path is resolved relative to the directory that contains
this file so that PyInstaller frozen builds find agent.cfg next to the EXE.
"""

from __future__ import annotations

import configparser
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_HOST: str = "127.0.0.1"
DEFAULT_PORT: int = 8765

# Resolve config file path relative to this module (works both when running
# as a Python script and when frozen by PyInstaller into an EXE).
if getattr(sys, "frozen", False):
    # PyInstaller sets sys._MEIPASS; the EXE lives in sys.executable's dir.
    _BASE_DIR = Path(sys.executable).parent
else:
    _BASE_DIR = Path(__file__).parent

CONFIG_FILE_PATH: Path = _BASE_DIR / "agent.cfg"

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AgentConfig:
    """Immutable resolved configuration."""

    host: str
    port: int
    source: str  # human-readable description of which source won

    def ws_url(self) -> str:
        return f"ws://{self.host}:{self.port}"

    def __str__(self) -> str:
        return f"{self.host}:{self.port} (from {self.source})"


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_config() -> AgentConfig:
    """
    Load and return the resolved AgentConfig.

    Resolution order:
      1. INTERACT_AGENT_PORT environment variable (overrides port only)
      2. agent.cfg  [agent] section  (host + port)
      3. Built-in defaults

    All parse errors are logged as warnings and the next source is tried.
    """
    host = DEFAULT_HOST
    port = DEFAULT_PORT
    source = "built-in defaults"

    # ── 3. Start with defaults ─────────────────────────────────────────────
    resolved_host = DEFAULT_HOST
    resolved_port = DEFAULT_PORT
    resolved_source = "built-in defaults"

    # ── 2. agent.cfg ──────────────────────────────────────────────────────
    if CONFIG_FILE_PATH.exists():
        cfg_parser = configparser.ConfigParser()
        try:
            cfg_parser.read(CONFIG_FILE_PATH, encoding="utf-8")
            section = "agent"
            if cfg_parser.has_section(section):
                if cfg_parser.has_option(section, "host"):
                    resolved_host = cfg_parser.get(section, "host").strip()
                if cfg_parser.has_option(section, "port"):
                    raw_port = cfg_parser.get(section, "port").strip()
                    try:
                        resolved_port = int(raw_port)
                    except ValueError:
                        log.warning(
                            "agent.cfg: invalid port value %r — using default %d",
                            raw_port,
                            DEFAULT_PORT,
                        )
                resolved_source = f"agent.cfg ({CONFIG_FILE_PATH})"
            else:
                log.warning(
                    "agent.cfg exists but has no [agent] section — using defaults"
                )
        except configparser.Error as exc:
            log.warning("agent.cfg parse error: %s — using defaults", exc)
    else:
        log.info("No agent.cfg found at %s — using defaults", CONFIG_FILE_PATH)

    # ── 1. Environment variable (highest priority — port only) ────────────
    env_port = os.environ.get("INTERACT_AGENT_PORT", "").strip()
    if env_port:
        try:
            resolved_port = int(env_port)
            resolved_source = f"INTERACT_AGENT_PORT env var (port={resolved_port})"
        except ValueError:
            log.warning(
                "INTERACT_AGENT_PORT=%r is not a valid integer — ignored",
                env_port,
            )

    return AgentConfig(host=resolved_host, port=resolved_port, source=resolved_source)
