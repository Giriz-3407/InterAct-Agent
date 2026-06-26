import logging
import os
import subprocess
import json
import requests
from packaging.version import Version
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QRectF, QPointF, QObject
from PySide6.QtGui import QColor, QPainter, QLinearGradient, QFont, QPen, QBrush, QGuiApplication
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QFrame,
    QProgressBar, QStackedWidget, QTextBrowser, QApplication
)
from src.ui import get_interact_logo_path, NotificationToast

# Dedicated updater logger
log = logging.getLogger("interact.updater")

# Centralized constants
CHECK_TIMEOUT = 10
DOWNLOAD_TIMEOUT = 30

def get_updates_dir() -> str:
    """Resolve and return the updates directory."""
    local_app_data = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    updates_dir = os.path.join(local_app_data, "InterAct", "Updates")
    os.makedirs(updates_dir, exist_ok=True)
    return updates_dir

def get_settings_filepath() -> str:
    """Resolve and return the settings file path."""
    local_app_data = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    settings_dir = os.path.join(local_app_data, "InterAct")
    os.makedirs(settings_dir, exist_ok=True)
    return os.path.join(settings_dir, "settings.json")

def get_skipped_version() -> str:
    """Read the skipped version from local settings."""
    filepath = get_settings_filepath()
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("skipped_version", "").strip().lstrip('vV')
        except Exception:
            pass
    return ""

def save_skipped_version(version: str):
    """Write skipped version to local settings."""
    filepath = get_settings_filepath()
    try:
        data = {}
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass
        data["skipped_version"] = version.strip().lstrip('vV')
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        log.info(f"Saved skipped version: {version}")
    except Exception as e:
        log.warning(f"Failed to save skipped version: {e}")

def validate_installer(filepath: str) -> bool:
    """Perform integrity validation on the downloaded installer file."""
    if not filepath:
        return False
    if not os.path.exists(filepath):
        return False
    if not filepath.lower().endswith(".exe"):
        return False
    if os.path.getsize(filepath) <= 0:
        return False
    return True

class UpdateCheckWorker(QThread):
    finished = Signal(bool, dict, str)  # success, release_info, error_msg

    def __init__(self, current_version: str, backend_url: str):
        super().__init__()
        self.current_version = current_version
        self.backend_url = backend_url

    def run(self):
        try:
            url = f"{self.backend_url.rstrip('/')}/api/version/latest"
            headers = {"User-Agent": f"InterAct-Desktop-Agent/{self.current_version}"}
            
            response = requests.get(url, headers=headers, timeout=CHECK_TIMEOUT)
            
            if response.status_code in (403, 429):
                self.finished.emit(False, {}, "API rate limit exceeded. Please try again later.")
                return
            elif response.status_code != 200:
                self.finished.emit(False, {}, f"Backend API returned error status: {response.status_code}")
                return
                
            data = response.json()
            if not isinstance(data, dict) or "version" not in data:
                self.finished.emit(False, {}, "Malformed API response: missing version.")
                return
                
            latest_version = data["version"]
            body = data.get("release_notes", "No release notes available.")
            
            # Resolve relative download URL to absolute URL
            raw_download_url = data.get("download_url", "/api/download/windows")
            if raw_download_url.startswith("http://") or raw_download_url.startswith("https://"):
                download_url = raw_download_url
            else:
                download_url = self.backend_url.rstrip('/') + '/' + raw_download_url.lstrip('/')
            
            # Compare versions
            current_clean = self.current_version.strip().lstrip('vV')
            latest_clean = latest_version.strip().lstrip('vV')
            
            if Version(latest_clean) > Version(current_clean):
                release_info = {
                    "latest_version": latest_version,
                    "release_notes": body,
                    "download_url": download_url
                }
                self.finished.emit(True, release_info, "")
            else:
                self.finished.emit(True, {}, "")
                
        except requests.exceptions.JSONDecodeError:
            self.finished.emit(False, {}, "Malformed API response: invalid JSON.")
        except requests.exceptions.RequestException as e:
            self.finished.emit(False, {}, f"Network connection failed: {str(e)}")
        except Exception as e:
            self.finished.emit(False, {}, f"Unexpected error checking updates: {str(e)}")

class UpdateDownloadWorker(QThread):
    progress = Signal(int, int)          # downloaded_bytes, total_bytes
    finished = Signal(bool, str, str)    # success, filepath, error_msg

    def __init__(self, download_url: str, version: str):
        super().__init__()
        self.download_url = download_url
        self.version = version
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        filepath = ""
        try:
            updates_dir = get_updates_dir()
            filename = f"InterAct-Desktop-Agent-{self.version}-Setup.exe"
            filepath = os.path.join(updates_dir, filename)
            
            # Clean up pre-existing file if it exists and wasn't validated
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except Exception as e:
                    log.warning(f"Could not remove existing file {filepath} before download: {e}")
            
            headers = {"User-Agent": f"InterAct-Desktop-Agent-Downloader/{self.version}"}
            response = requests.get(self.download_url, headers=headers, stream=True, timeout=DOWNLOAD_TIMEOUT)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            bytes_downloaded = 0
            
            with open(filepath, "wb") as f:
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if self._is_cancelled:
                        break
                    if chunk:
                        f.write(chunk)
                        bytes_downloaded += len(chunk)
                        self.progress.emit(bytes_downloaded, total_size)
            
            if self._is_cancelled:
                self._delete_partial(filepath)
                self.finished.emit(False, "", "Download cancelled by user.")
                return
            
            if total_size > 0 and bytes_downloaded != total_size:
                raise Exception("Corrupted download: File size mismatch.")
                
            self.finished.emit(True, filepath, "")
            
        except Exception as e:
            self._delete_partial(filepath)
            self.finished.emit(False, "", f"Failed to download installer: {str(e)}")

    def _delete_partial(self, filepath: str):
        if filepath and os.path.exists(filepath):
            try:
                os.remove(filepath)
                log.info(f"Deleted partial/interrupted download: {filepath}")
            except Exception as e:
                log.warning(f"Could not delete partial download {filepath}: {e}")

class UpdateDialog(QWidget):
    def __init__(self, current_ver: str, latest_ver: str, notes: str, download_url: str, parent=None):
        super().__init__(parent)
        self.current_ver = current_ver
        self.latest_ver = latest_ver
        self.notes = notes
        self.download_url = download_url
        self.download_worker = None
        
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Dialog
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(440, 380)
        
        # Center the window
        screen = QGuiApplication.primaryScreen().geometry()
        self.move((screen.width() - self.width()) // 2, (screen.height() - self.height()) // 2)
        
        self._drag_pos = None
        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet("""
            QWidget {
                color: #f3f4f6;
                font-family: 'Segoe UI', Arial;
            }
            QLabel {
                background: transparent;
            }
            QPushButton {
                font-size: 11px;
                font-weight: 600;
                border-radius: 6px;
                padding: 6px 12px;
            }
            QPushButton#primaryBtn {
                background-color: #4f46e5;
                border: 1px solid #6366f1;
            }
            QPushButton#primaryBtn:hover {
                background-color: #4338ca;
            }
            QPushButton#secondaryBtn {
                background-color: #1e1b4b;
                border: 1px solid #312e81;
            }
            QPushButton#secondaryBtn:hover {
                background-color: #312e81;
            }
            QPushButton#closeIconBtn {
                background: transparent;
                border: none;
                font-size: 16px;
                color: #9ca3af;
                font-weight: normal;
                padding: 2px;
            }
            QPushButton#closeIconBtn:hover {
                color: #ffffff;
            }
            QTextBrowser {
                background-color: rgba(255, 255, 255, 6);
                border: 1px solid rgba(255, 255, 255, 8);
                border-radius: 6px;
                color: #d1d5db;
                padding: 8px;
                font-size: 11px;
            }
            QScrollBar:vertical {
                background: rgba(255, 255, 255, 4);
                width: 6px;
                margin: 0px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: rgba(139, 92, 246, 120);
                min-height: 20px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(139, 92, 246, 180);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QProgressBar {
                border: 1px solid #312e81;
                border-radius: 5px;
                background-color: #1e1b4b;
                text-align: center;
                color: #ffffff;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8b5cf6, stop:1 #4f46e5);
                border-radius: 4px;
            }
        """)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 60, 15, 15)  # 60 top margin for title bar
        
        # Title bar close button
        self.close_btn = QPushButton("×", self)
        self.close_btn.setObjectName("closeIconBtn")
        self.close_btn.setGeometry(self.width() - 34, 10, 24, 24)
        self.close_btn.clicked.connect(self.close)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Stacked widget for pages
        self.stack = QStackedWidget(self)
        main_layout.addWidget(self.stack)

        # ── PAGE 0: Update Prompt ───────────────────────────────────────────
        prompt_page = QWidget()
        prompt_layout = QVBoxLayout(prompt_page)
        prompt_layout.setContentsMargins(5, 5, 5, 5)
        prompt_layout.setSpacing(12)
        
        info_label = QLabel("A new version of InterAct Desktop Agent is available.", prompt_page)
        info_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Medium))
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #e5e7eb;")
        prompt_layout.addWidget(info_label)
        
        ver_layout = QHBoxLayout()
        ver_layout.setSpacing(10)
        
        curr_box = QFrame(prompt_page)
        curr_box.setStyleSheet("QFrame { background-color: rgba(255, 255, 255, 8); border: 1px solid rgba(255, 255, 255, 10); border-radius: 6px; }")
        curr_box_layout = QVBoxLayout(curr_box)
        curr_box_layout.setContentsMargins(10, 8, 10, 8)
        curr_lbl_title = QLabel("Installed Version", curr_box)
        curr_lbl_title.setStyleSheet("font-size: 10px; color: #9ca3af; border: none;")
        curr_lbl_val = QLabel(f"v{self.current_ver}", curr_box)
        curr_lbl_val.setStyleSheet("font-size: 12px; font-weight: bold; color: #f3f4f6; border: none;")
        curr_box_layout.addWidget(curr_lbl_title)
        curr_box_layout.addWidget(curr_lbl_val)
        
        late_box = QFrame(prompt_page)
        late_box.setStyleSheet("QFrame { background-color: rgba(139, 92, 246, 12); border: 1px solid rgba(139, 92, 246, 30); border-radius: 6px; }")
        late_box_layout = QVBoxLayout(late_box)
        late_box_layout.setContentsMargins(10, 8, 10, 8)
        late_lbl_title = QLabel("Latest Version", late_box)
        late_lbl_title.setStyleSheet("font-size: 10px; color: #a78bfa; border: none;")
        late_lbl_val = QLabel(f"v{self.latest_ver}", late_box)
        late_lbl_val.setStyleSheet("font-size: 12px; font-weight: bold; color: #c084fc; border: none;")
        late_box_layout.addWidget(late_lbl_title)
        late_box_layout.addWidget(late_lbl_val)
        
        ver_layout.addWidget(curr_box)
        ver_layout.addWidget(late_box)
        prompt_layout.addLayout(ver_layout)
        
        notes_title = QLabel("What's New:", prompt_page)
        notes_title.setFont(QFont("Segoe UI", 9.5, QFont.Weight.Medium))
        notes_title.setStyleSheet("color: #9ca3af;")
        prompt_layout.addWidget(notes_title)
        
        self.notes_browser = QTextBrowser(prompt_page)
        self.notes_browser.setMarkdown(self.notes)
        self.notes_browser.setOpenExternalLinks(True)
        prompt_layout.addWidget(self.notes_browser)
        
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        
        self.skip_btn = QPushButton("Skip Version", prompt_page)
        self.skip_btn.setObjectName("secondaryBtn")
        self.skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.skip_btn.clicked.connect(self._skip_version)
        
        self.later_btn = QPushButton("Later", prompt_page)
        self.later_btn.setObjectName("secondaryBtn")
        self.later_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.later_btn.clicked.connect(self.close)
        
        self.update_btn = QPushButton("Update Now", prompt_page)
        self.update_btn.setObjectName("primaryBtn")
        self.update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_btn.clicked.connect(self._start_download)
        
        btn_layout.addWidget(self.skip_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.later_btn)
        btn_layout.addWidget(self.update_btn)
        prompt_layout.addLayout(btn_layout)
        
        self.stack.addWidget(prompt_page)

        # ── PAGE 1: Downloading ─────────────────────────────────────────────
        download_page = QWidget()
        download_layout = QVBoxLayout(download_page)
        download_layout.setContentsMargins(5, 20, 5, 20)
        download_layout.setSpacing(15)
        download_layout.addStretch()
        
        self.dl_status_label = QLabel("Downloading update...", download_page)
        self.dl_status_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Medium))
        self.dl_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        download_layout.addWidget(self.dl_status_label)
        
        self.progress_bar = QProgressBar(download_page)
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        download_layout.addWidget(self.progress_bar)
        
        self.dl_info_label = QLabel("Starting download...", download_page)
        self.dl_info_label.setFont(QFont("Segoe UI", 9))
        self.dl_info_label.setStyleSheet("color: #9ca3af;")
        self.dl_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        download_layout.addWidget(self.dl_info_label)
        
        download_layout.addStretch()
        
        cancel_btn_layout = QHBoxLayout()
        cancel_btn_layout.addStretch()
        self.cancel_dl_btn = QPushButton("Cancel", download_page)
        self.cancel_dl_btn.setObjectName("secondaryBtn")
        self.cancel_dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_dl_btn.clicked.connect(self._cancel_download)
        cancel_btn_layout.addWidget(self.cancel_dl_btn)
        cancel_btn_layout.addStretch()
        download_layout.addLayout(cancel_btn_layout)
        
        self.stack.addWidget(download_page)

        # ── PAGE 2: Error ───────────────────────────────────────────────────
        error_page = QWidget()
        error_layout = QVBoxLayout(error_page)
        error_layout.setContentsMargins(5, 20, 5, 20)
        error_layout.setSpacing(15)
        error_layout.addStretch()
        
        warning_icon = QLabel("⚠️", error_page)
        warning_icon.setFont(QFont("Segoe UI", 24))
        warning_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        error_layout.addWidget(warning_icon)
        
        self.error_label = QLabel("Failed to update.", error_page)
        self.error_label.setFont(QFont("Segoe UI", 10.5))
        self.error_label.setStyleSheet("color: #f87171;")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setWordWrap(True)
        error_layout.addWidget(self.error_label)
        
        error_layout.addStretch()
        
        error_btn_layout = QHBoxLayout()
        error_btn_layout.setSpacing(10)
        error_btn_layout.addStretch()
        
        self.error_close_btn = QPushButton("Close", error_page)
        self.error_close_btn.setObjectName("secondaryBtn")
        self.error_close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.error_close_btn.clicked.connect(self.close)
        
        self.retry_btn = QPushButton("Retry Download", error_page)
        self.retry_btn.setObjectName("primaryBtn")
        self.retry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.retry_btn.clicked.connect(self._start_download)
        
        error_btn_layout.addWidget(self.error_close_btn)
        error_btn_layout.addWidget(self.retry_btn)
        error_btn_layout.addStretch()
        error_layout.addLayout(error_btn_layout)
        
        self.stack.addWidget(error_page)

    def _skip_version(self):
        save_skipped_version(self.latest_ver)
        self.close()

    def _start_download(self):
        # 1. Clicking "Update Now" multiple times rapidly should only start one download
        if self.download_worker and self.download_worker.isRunning():
            return
        
        self.update_btn.setEnabled(False)
        self.skip_btn.setEnabled(False)
        
        updates_dir = get_updates_dir()
        filename = f"InterAct-Desktop-Agent-{self.latest_ver}-Setup.exe"
        filepath = os.path.join(updates_dir, filename)
        
        # 2. Preserve downloaded installer: if correct installer exists and passes validation, reuse it
        if validate_installer(filepath):
            log.info(f"Reusing verified installer: {filepath}")
            self.stack.setCurrentIndex(1)
            self.progress_bar.setValue(100)
            self.dl_status_label.setText("Installer verified!")
            self.dl_info_label.setText("Reusing downloaded file...")
            QTimer.singleShot(1000, lambda: self._launch_installer(filepath))
            return
            
        self.stack.setCurrentIndex(1)
        self.progress_bar.setValue(0)
        self.dl_status_label.setText("Downloading update...")
        self.dl_info_label.setText("Connecting...")
        
        self.download_worker = UpdateDownloadWorker(self.download_url, self.latest_ver)
        self.download_worker.progress.connect(self._on_download_progress)
        self.download_worker.finished.connect(self._on_download_finished)
        self.download_worker.start()

    def _on_download_progress(self, downloaded: int, total: int):
        if total > 0:
            pct = int((downloaded / total) * 100)
            self.progress_bar.setValue(pct)
            dl_mb = downloaded / (1024 * 1024)
            tot_mb = total / (1024 * 1024)
            self.dl_info_label.setText(f"Downloaded {dl_mb:.1f} MB of {tot_mb:.1f} MB ({pct}%)")
        else:
            dl_mb = downloaded / (1024 * 1024)
            self.dl_info_label.setText(f"Downloaded {dl_mb:.1f} MB")

    def _on_download_finished(self, success: bool, filepath: str, error_msg: str):
        self.update_btn.setEnabled(True)
        self.skip_btn.setEnabled(True)
        
        if success:
            self.dl_status_label.setText("Download complete!")
            self.dl_info_label.setText("Launching installer...")
            QTimer.singleShot(1000, lambda: self._launch_installer(filepath))
        else:
            if "cancelled" in error_msg.lower():
                self.stack.setCurrentIndex(0)
            else:
                self.error_label.setText(error_msg)
                self.stack.setCurrentIndex(2)

    def _cancel_download(self):
        if self.download_worker and self.download_worker.isRunning():
            self.download_worker.cancel()
            self.download_worker.wait()
        self.stack.setCurrentIndex(0)

    def _launch_installer(self, filepath: str):
        try:
            if validate_installer(filepath):
                log.info(f"Launching installer asynchronously after shutdown: {filepath}")
                
                pid = os.getpid()
                CREATE_NO_WINDOW = 0x08000000
                DETACHED_PROCESS = 0x00000008
                creationflags = CREATE_NO_WINDOW | DETACHED_PROCESS

                # Detached PowerShell script that waits for our PID to terminate, then runs the installer
                cmd_args = [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    f"Start-Sleep -Milliseconds 100; "
                    f"$p = Get-Process -Id {pid} -ErrorAction SilentlyContinue; "
                    f"if ($p) {{ $p | Wait-Process }}; "
                    f"Start-Process -FilePath '{filepath}'"
                ]
                
                subprocess.Popen(cmd_args, creationflags=creationflags)
                
                # Initiate immediate graceful shutdown of the Qt application
                log.info("[Updater] Spawning updater process and quitting application...")
                QApplication.quit()
            else:
                raise ValueError("Downloaded file integrity check failed.")
        except Exception as e:
            log.error(f"Failed to launch installer: {e}")
            self.error_label.setText(f"Failed to launch installer: {str(e)}")
            self.stack.setCurrentIndex(2)

    def closeEvent(self, event):
        if self.download_worker and self.download_worker.isRunning():
            self.download_worker.cancel()
            self.download_worker.wait()
        event.accept()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if event.position().y() < 50:
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bg_rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        bg_grad = QLinearGradient(0, 0, 0, self.height())
        bg_grad.setColorAt(0.0, QColor(14, 12, 24, 245))
        bg_grad.setColorAt(1.0, QColor(8, 7, 14, 250))
        
        painter.setBrush(QBrush(bg_grad))
        painter.setPen(QPen(QColor(139, 92, 246, 80), 1.5))
        painter.drawRoundedRect(bg_rect, 12, 12)

        painter.setPen(QPen(QColor(255, 255, 255, 12), 1.0))
        painter.drawLine(2, 48, self.width() - 2, 48)

        logo_path = get_interact_logo_path(0.35)
        bounds = logo_path.boundingRect()
        painter.save()
        painter.translate(18, 24 - bounds.center().y())
        painter.setBrush(QBrush(QColor("#a78bfa")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(logo_path)
        painter.restore()

        painter.setFont(QFont("Segoe UI", 11.5, QFont.Weight.DemiBold))
        painter.setPen(QColor("#f3f4f6"))
        painter.drawText(46, 16, 200, 24, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "Software Update")

class UpdateManager(QObject):
    def __init__(self, current_version: str, backend_url: str, parent_window=None):
        super().__init__()
        self.current_version = current_version
        self.backend_url = backend_url
        self.parent_window = parent_window
        self.check_worker = None
        self.dialog = None
        self.interactive = False
        self._toast = None

    def check_for_updates(self, interactive: bool = False):
        """Asynchronously check for updates. Can be triggered at startup or manually."""
        self.interactive = interactive
        
        if self.interactive:
            log.info("Manual check for updates initiated...")
            self._toast = NotificationToast("Checking for updates...", is_success=True)
            self._toast.show()
        else:
            log.info(f"Startup check for updates initiated against '{self.backend_url}'...")

        self.check_worker = UpdateCheckWorker(self.current_version, self.backend_url)
        self.check_worker.finished.connect(self._on_check_finished)
        self.check_worker.start()

    def _on_check_finished(self, success: bool, release_info: dict, error_msg: str):
        if not success:
            log.warning(f"Update check failed: {error_msg}")
            if self.interactive:
                self._toast = NotificationToast(f"Update check failed: {error_msg}", is_success=False)
                self._toast.show()
            return
        
        if not release_info:
            log.info("Desktop Agent is up to date.")
            # Clean up older installers only, keeping our current version (which is up-to-date)
            self.cleanup_updates(keep_version=self.current_version)
            if self.interactive:
                self._toast = NotificationToast("InterAct Desktop Agent is up to date.", is_success=True)
                self._toast.show()
            return

        latest_ver = release_info['latest_version']
        latest_clean = latest_ver.strip().lstrip('vV')
        skipped_clean = get_skipped_version()

        # Clean up older installer files, keeping the latest release installer
        self.cleanup_updates(keep_version=latest_clean)

        # Skip version check (only skipped if check is not manually triggered)
        if not self.interactive and latest_clean == skipped_clean:
            log.info(f"Version v{latest_ver} is skipped by user. Ignoring startup dialog.")
            return

        log.info(f"New version available: {latest_ver}")
        if self.interactive:
            if self._toast:
                self._toast.close()
                self._toast = None
                
        self.dialog = UpdateDialog(
            current_ver=self.current_version,
            latest_ver=latest_ver,
            notes=release_info["release_notes"],
            download_url=release_info["download_url"],
            parent=self.parent_window
        )
        self.dialog.show()

    def cleanup_updates(self, keep_version: str = None):
        """Remove older installer setup files, preserving only the keep_version installer."""
        try:
            updates_dir = get_updates_dir()
            keep_filename = f"InterAct-Desktop-Agent-{keep_version}-Setup.exe" if keep_version else None
            
            for filename in os.listdir(updates_dir):
                if filename.endswith(".exe") and "InterAct-Desktop-Agent" in filename:
                    if keep_filename and filename == keep_filename:
                        # Preserve correct version installer
                        continue
                    
                    filepath = os.path.join(updates_dir, filename)
                    try:
                        os.remove(filepath)
                        log.info(f"Cleaned up older installer: {filename}")
                    except Exception as e:
                        log.warning(f"Could not remove older installer {filename}: {e}")
        except Exception as e:
            log.warning(f"Error during installer cleanup: {e}")
