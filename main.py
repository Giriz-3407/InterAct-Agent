"""
main.py — InterAct Desktop Agent, RC1 entry point.

Launches the transparent fullscreen overlay and a local WebSocket server
that accepts cursor events from external clients.

Changes from Phase 3:
  - Configuration loaded from env var / agent.cfg / defaults (config.py)
  - WebSocket server sends agent_info handshake on every client connection
  - Structured logging to file (%LOCALAPPDATA%/InterAct/logs/) and stderr
  - File logging enables console=False PyInstaller builds (no terminal needed)
  - Graceful Ctrl+C shutdown (unchanged)

Architecture:
  Browser ↔ ws://127.0.0.1:<port> ↔ Desktop Agent EXE (this process)

Usage:
    python main.py                         # start agent (reads agent.cfg)
    INTERACT_AGENT_PORT=9000 python main.py   # override port via env
    python test_client.py                  # single-cursor demo
    python test_client.py --multi          # two simultaneous cursors
    python test_client.py --remove         # cursor removal demo
"""

import logging
import os
import signal
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from src.overlay import LaserPointerOverlay
from src.ws_server import CursorBridge, start_websocket_server
from src.config import load_config
from src.agent_version import AGENT_VERSION, PROTOCOL_VERSION
from src.ui import SplashWindow, NotificationToast, InteractiveStatusWindow, TrayManager
from src.updater import UpdateManager

# ── Centralized Single-Instance Constants ───────────────────────────────────
INTERACT_AGENT_MUTEX: str = "Global\\InterActAgentSingleInstanceMutex"
INTERACT_AGENT_IPC_SERVER: str = "InterActAgentLocalServer"

# Keep a reference to the mutex handle to prevent it from being garbage collected
_MUTEX_HOLDER = None


# ---------------------------------------------------------------------------
# Logging setup — file + stderr, no console window required
# ---------------------------------------------------------------------------

def _setup_logging() -> Path:
    """
    Configure the root logger to write to both a rotating file and stderr.

    Log file location (in priority order):
      1. Frozen EXE: %LOCALAPPDATA%/InterAct/logs/interact-agent.log
      2. Dev run   : ./logs/interact-agent.log  (relative to this file)

    Returns the resolved log file path for startup reporting.
    """
    import logging.handlers

    # ── Resolve log directory ─────────────────────────────────────────────
    if getattr(sys, "frozen", False):
        local_app_data = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        log_dir = Path(local_app_data) / "InterAct" / "logs"
    else:
        log_dir = Path(__file__).parent / "logs"

    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "interact-agent.log"

    # ── Formatter — structured single-line format ─────────────────────────
    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    # ── File handler — 5 MB max, keep 3 rotated files ────────────────────
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    # ── Console handler — INFO and above (visible during dev) ─────────────
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(fmt)

    # ── Root logger ───────────────────────────────────────────────────────
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)   # file gets DEBUG, console gets INFO
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    return log_file


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Application Lifecycle Manager
# ---------------------------------------------------------------------------

class AgentApp:
    """Manages the lifecycle of the primary Desktop Agent instance."""

    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.overlay = None
        self.bridge = None
        self.status_window = None
        self.tray_manager = None
        self.splash = None
        self.local_server = None

    def run(self, app: QApplication) -> int:
        log.info("[Agent] Starting services")

        # Connect aboutToQuit signal for clean exit cleanup
        app.aboutToQuit.connect(self.cleanup)

        # 1. Start QLocalServer to listen for duplicate launches
        QLocalServer.removeServer(INTERACT_AGENT_IPC_SERVER)
        self.local_server = QLocalServer()
        self.local_server.newConnection.connect(self._handle_ipc_connection)
        if not self.local_server.listen(INTERACT_AGENT_IPC_SERVER):
            log.error("[Agent] Failed to start QLocalServer: %s", self.local_server.errorString())

        # 2. Show splash screen immediately
        self.splash = SplashWindow()
        self.splash.show()

        # 3. Initialize overlay (hidden/transparent until fully ready)
        self.overlay = LaserPointerOverlay()
        
        # 4. Initialize CursorBridge & connect signals
        self.bridge = CursorBridge()
        self.bridge.cursor_moved.connect(self.overlay.set_cursor_position)
        self.bridge.cursor_clicked.connect(self.overlay.add_click_ripple)
        self.bridge.cursor_removed.connect(self.overlay.remove_cursor)
        self.bridge.annotation_updated.connect(self.overlay.set_annotation)
        self.bridge.annotation_cleared.connect(self.overlay.clear_annotations)
        self.bridge.spotlight_updated.connect(self.overlay.set_spotlight)
        self.bridge.client_disconnected.connect(self.overlay.clear_spotlight_on_disconnect)

        self.bridge.server_started.connect(self._on_server_started)

        self.splash.set_status_text("Preparing collaboration overlay...")

        # 5. Start WebSocket server on background daemon thread
        start_websocket_server(self.bridge, host=self.cfg.host, port=self.cfg.port)

        return app.exec()

    def _on_server_started(self) -> None:
        log.info("[Agent] WebSocket server ready")
        self.splash.set_status_text("✓ InterAct Agent Ready")
        # Let the "Ready" message show for a brief moment before completing startup
        QTimer.singleShot(1500, self._complete_startup)

    def _complete_startup(self) -> None:
        self.splash.close_gracefully()

        # Render overlay cursors
        self.overlay.show()

        # Create status window (initially open/shown on first launch)
        self.status_window = InteractiveStatusWindow(self.cfg.host, self.cfg.port)
        self.status_window.restart_requested.connect(self._handle_restart)

        # Create tray manager
        self.tray_manager = TrayManager(QApplication.instance(), self)

        # Open the control window on startup
        self.status_window.show_activated()

        # Show success startup toast notification
        self.success_toast = NotificationToast("✓ InterAct Collaboration Agent Running", is_success=True)
        self.success_toast.show()

        log.info("[Agent] Agent ready")

        # Initialize the Auto-Update manager and run startup check
        self.update_manager = UpdateManager(AGENT_VERSION, self.cfg.backend_url, parent_window=self.status_window)
        self.update_manager.check_for_updates(interactive=False)

    def _handle_ipc_connection(self) -> None:
        socket = self.local_server.nextPendingConnection()
        if socket:
            if socket.waitForReadyRead(500):
                data = socket.readAll().data()
                if data == b"activate":
                    log.info("[Agent] Existing instance detected — activating status window.")
                    if self.status_window:
                        self.status_window.show_activated()
                        # Show confirmation toast in running instance
                        self.activation_toast = NotificationToast("InterAct Agent is already running.", is_success=False)
                        self.activation_toast.show()
            socket.disconnectFromServer()
            socket.deleteLater()

    def _handle_restart(self) -> None:
        log.info("[Agent] Restarting agent...")
        
        # 1. Clean shutdown of current instance first
        self.cleanup()
        
        # Release the single-instance mutex explicitly so the restarted process can acquire it immediately
        global _MUTEX_HOLDER
        if _MUTEX_HOLDER:
            import ctypes
            ctypes.windll.kernel32.CloseHandle(_MUTEX_HOLDER)
            _MUTEX_HOLDER = None
            log.info("[Agent] Mutex released for restart.")

        # 2. Start a new agent process
        import subprocess
        if getattr(sys, "frozen", False):
            subprocess.Popen([sys.executable] + sys.argv[1:])
        else:
            main_script = Path(__file__).resolve()
            subprocess.Popen([sys.executable, str(main_script)] + sys.argv[1:])
            
        # 3. Exit the current process
        QApplication.quit()

    def cleanup(self) -> None:
        """Clean up resources before quitting application."""
        if getattr(self, "_cleaned_up", False):
            return
        self._cleaned_up = True
        
        log.info("[Agent] Cleaning up resources before exit.")
        if self.local_server:
            self.local_server.close()
            log.info("[Agent] IPC local server closed.")
        if self.tray_manager:
            self.tray_manager.cleanup()
            log.info("[Agent] Tray icon removed.")
        if hasattr(self, "update_manager") and self.update_manager:
            if self.update_manager.check_worker and self.update_manager.check_worker.isRunning():
                self.update_manager.check_worker.quit()
                self.update_manager.check_worker.wait()
            if self.update_manager.dialog:
                self.update_manager.dialog.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    global _MUTEX_HOLDER
    log_file = _setup_logging()

    # ── 1. Single Instance Check (Win32 Mutex) ─────────────────────────────
    # Check this before ANY services are initialized.
    import ctypes
    kernel32 = ctypes.windll.kernel32
    ERROR_ALREADY_EXISTS = 183

    log.info("[Agent] Attempting single-instance lock")
    mutex_handle = kernel32.CreateMutexW(None, False, INTERACT_AGENT_MUTEX)
    last_error = kernel32.GetLastError()

    if last_error == ERROR_ALREADY_EXISTS:
        log.warning("[Agent] Existing instance detected — aborting secondary launch.")
        
        # We need a brief QApplication to send the socket signal
        app = QApplication(sys.argv)
        
        # Send activation command to primary instance
        socket = QLocalSocket()
        socket.connectToServer(INTERACT_AGENT_IPC_SERVER)
        if socket.waitForConnected(500):
            socket.write(b"activate")
            socket.waitForBytesWritten(500)
            socket.disconnectFromServer()

        # Close local duplicate mutex handle to be clean
        kernel32.CloseHandle(mutex_handle)
        return 0

    # Lock successfully acquired! Keep handle alive
    _MUTEX_HOLDER = mutex_handle
    log.info("[Agent] Lock acquired")

    # ── 2. Initialize primary instance ──────────────────────────────────────
    cfg = load_config()
    log.info(
        "InterAct Agent %s starting (protocol_version=%d)",
        AGENT_VERSION,
        PROTOCOL_VERSION,
    )
    log.info("Config resolved: %s", cfg)
    log.info("Log file: %s", log_file)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False) # Keep running in background tray

    # ── Allow Ctrl+C from the terminal to terminate cleanly ────────────────
    # Qt blocks Python signal handlers while its event loop runs.
    # We install a short-interval timer that lets Python's signal handling
    # machinery run, so Ctrl+C (SIGINT) is honoured even in frozen builds.
    def _handle_sigint(*_):
        log.info("Received SIGINT — shutting down cleanly.")
        app.quit()

    signal.signal(signal.SIGINT, _handle_sigint)

    _sigint_timer = QTimer()
    _sigint_timer.setInterval(250)          # check every 250 ms
    _sigint_timer.timeout.connect(lambda: None)  # no-op wakes the event loop
    _sigint_timer.start()

    agent_app = AgentApp(cfg)
    return agent_app.run(app)


if __name__ == "__main__":
    sys.exit(main())
