"""
ui.py — Custom Qt UI components for InterAct Desktop Agent.

Implements a dark glassmorphic UI matching InterAct branding:
  - SplashWindow: Frameless startup splash with rotation animations
  - NotificationToast: Translucent notification popups that fade in/out
  - StatusWindow: Borderless draggable status dashboard window
  - TrayManager: System tray icon with context menu
"""

from __future__ import annotations

import sys
from typing import Optional
from PySide6.QtCore import Qt, QTimer, QRect, QPoint, QRectF, QPointF, QObject, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPainterPath,
    QRadialGradient,
    QLinearGradient,
    QGuiApplication,
    QFont,
    QPen,
    QIcon,
    QPixmap,
    QBrush,
)
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QSystemTrayIcon,
    QMenu,
)

# ---------------------------------------------------------------------------
# InterAct Logo Vector Path
# ---------------------------------------------------------------------------

def get_interact_logo_path(s: float = 1.0) -> QPainterPath:
    """Create the custom QPainterPath representing the InterAct logo."""
    path = QPainterPath()
    path.moveTo((130.857 - 84.9859) * s, (99.5792 - 64.1122) * s)
    path.cubicTo(
        (125.329 - 84.9859) * s, (100.271 - 64.1122) * s,
        (123.353 - 84.9859) * s, (100.63 - 64.1122) * s,
        (121.748 - 84.9859) * s, (102.18 - 64.1122) * s,
    )
    path.cubicTo(
        (120.143 - 84.9859) * s, (103.73 - 64.1122) * s,
        (119.714 - 84.9859) * s, (105.693 - 64.1122) * s,
        (118.83 - 84.9859) * s, (111.194 - 64.1122) * s,
    )
    path.cubicTo(
        (117.946 - 84.9859) * s, (116.694 - 64.1122) * s,
        (117.462 - 84.9859) * s, (121.807 - 64.1122) * s,
        (112.294 - 84.9859) * s, (124.474 - 64.1122) * s,
    )
    path.cubicTo(
        (107.126 - 84.9859) * s, (127.142 - 64.1122) * s,
        (102.496 - 84.9859) * s, (121.545 - 64.1122) * s,
        (100.619 - 84.9859) * s, (116.389 - 64.1122) * s,
    )
    path.cubicTo(
        (98.7421 - 84.9859) * s, (111.232 - 64.1122) * s,
        (84.7765 - 84.9859) * s, (75.9305 - 64.1122) * s,
        (84.7765 - 84.9859) * s, (75.9305 - 64.1122) * s,
    )
    path.cubicTo(
        (84.7765 - 84.9859) * s, (75.9305 - 64.1122) * s,
        (80.9772 - 84.9859) * s, (67.9834 - 64.1122) * s,
        0.0, 0.0,
    )
    path.cubicTo(
        (88.9946 - 84.9859) * s, (60.241 - 64.1122) * s,
        (96.8035 - 84.9859) * s, (64.3162 - 64.1122) * s,
        (96.8035 - 84.9859) * s, (64.3162 - 64.1122) * s,
    )
    path.cubicTo(
        (96.8035 - 84.9859) * s, (64.3162 - 64.1122) * s,
        (131.596 - 84.9859) * s, (79.5053 - 64.1122) * s,
        (136.684 - 84.9859) * s, (81.5613 - 64.1122) * s,
    )
    path.cubicTo(
        (141.772 - 84.9859) * s, (83.6173 - 64.1122) * s,
        (147.203 - 84.9859) * s, (88.4397 - 64.1122) * s,
        (144.357 - 84.9859) * s, (93.5115 - 64.1122) * s,
    )
    path.cubicTo(
        (141.511 - 84.9859) * s, (98.5833 - 64.1122) * s,
        (136.384 - 84.9859) * s, (98.8878 - 64.1122) * s,
        (130.857 - 84.9859) * s, (99.5792 - 64.1122) * s,
    )
    path.closeSubpath()
    return path


def create_tray_icon() -> QIcon:
    """Create a high-quality vector-drawn tray icon dynamically."""
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Gradient circle background
    grad = QLinearGradient(0, 0, 32, 32)
    grad.setColorAt(0.0, QColor("#8b5cf6")) # Violet accent
    grad.setColorAt(1.0, QColor("#4f46e5")) # Indigo accent

    painter.setBrush(QBrush(grad))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(2, 2, 28, 28)

    # Logo in center
    logo_path = get_interact_logo_path(0.24)
    rect = logo_path.boundingRect()
    painter.translate(16 - rect.center().x(), 16 - rect.center().y())
    painter.setBrush(QBrush(QColor(255, 255, 255)))
    painter.drawPath(logo_path)
    painter.end()

    return QIcon(pixmap)

# ---------------------------------------------------------------------------
# Splash Screen
# ---------------------------------------------------------------------------

class SplashWindow(QWidget):
    """Frameless startup splash screen with rotation loading animation."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(360, 240)

        # Center on primary monitor
        screen = QGuiApplication.primaryScreen().geometry()
        self.move((screen.width() - self.width()) // 2, (screen.height() - self.height()) // 2)

        # Set up rotation timer for loading spinner
        self._rotation = 0.0
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(20) # ~50 FPS
        self._anim_timer.timeout.connect(self._update_animation)
        self._anim_timer.start()

        # Layout
        self._status_text = "Starting InterAct Agent..."
        
        # Soft entry fade
        self.setWindowOpacity(0.0)
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(300)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(0.95)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_anim.start()

    def set_status_text(self, text: str) -> None:
        """Update user-friendly status text and trigger paint update."""
        self._status_text = text
        self.update()

    def _update_animation(self) -> None:
        self._rotation = (self._rotation + 3) % 360
        self.update()

    def close_gracefully(self) -> None:
        """Fade out and close."""
        self._fade_anim.stop()
        self._fade_anim.setDuration(250)
        self._fade_anim.setStartValue(self.windowOpacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.finished.connect(self.close)
        self._fade_anim.start()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw glassmorphic background
        bg_rect = QRectF(self.rect())
        bg_rect.adjust(2, 2, -2, -2) # padding for shadow/border
        
        # Background gradient
        bg_grad = QLinearGradient(0, 0, 0, self.height())
        bg_grad.setColorAt(0.0, QColor(14, 13, 22, 245))  # deep dark violet
        bg_grad.setColorAt(1.0, QColor(9, 7, 16, 250))
        
        # Glowing border pen
        border_pen = QPen(QColor(139, 92, 246, 70), 1.5)
        
        painter.setBrush(QBrush(bg_grad))
        painter.setPen(border_pen)
        painter.drawRoundedRect(bg_rect, 16, 16)

        # Draw logo (centered at top-half)
        logo_center_x = self.width() / 2.0
        logo_center_y = 90.0
        
        # Glow behind logo
        glow = QRadialGradient(logo_center_x, logo_center_y, 45)
        glow.setColorAt(0.0, QColor(139, 92, 246, 40))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(glow))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(logo_center_x - 50, logo_center_y - 50, 100, 100)

        # Spinner ring around logo
        painter.save()
        painter.translate(logo_center_x, logo_center_y)
        painter.rotate(self._rotation)
        
        spinner_pen = QPen(QColor(139, 92, 246, 180), 2.0)
        spinner_pen.setStyle(Qt.PenStyle.CustomDashLine)
        spinner_pen.setDashPattern([6.0, 12.0])
        painter.setPen(spinner_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(0, 0), 38, 38)
        painter.restore()

        # Draw actual vector logo
        painter.save()
        logo_path = get_interact_logo_path(0.65)
        bounds = logo_path.boundingRect()
        painter.translate(logo_center_x - bounds.center().x(), logo_center_y - bounds.center().y())
        
        # Logo fill
        logo_grad = QLinearGradient(bounds.topLeft(), bounds.bottomRight())
        logo_grad.setColorAt(0.0, QColor("#a78bfa"))
        logo_grad.setColorAt(1.0, QColor("#6366f1"))
        
        painter.setBrush(QBrush(logo_grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(logo_path)
        painter.restore()

        # Title Text
        painter.setFont(QFont("Segoe UI", 15, QFont.Weight.DemiBold))
        painter.setPen(QColor("#f3f4f6"))
        painter.drawText(QRect(0, 145, self.width(), 30), Qt.AlignmentFlag.AlignCenter, "InterAct Collaboration")

        # Subtitle Status Text
        painter.setFont(QFont("Segoe UI", 10))
        painter.setPen(QColor("#9ca3af"))
        painter.drawText(QRect(0, 180, self.width(), 25), Qt.AlignmentFlag.AlignCenter, self._status_text)

# ---------------------------------------------------------------------------
# Notification Toast
# ---------------------------------------------------------------------------

class NotificationToast(QWidget):
    """Temporary notification toast that fades in and out."""

    def __init__(self, message: str, is_success: bool = True) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(340, 68)

        # Position at bottom-right corner of screen (just above taskbar)
        screen = QGuiApplication.primaryScreen().geometry()
        margin = 25
        self.move(screen.width() - self.width() - margin, screen.height() - self.height() - 55)

        self._message = message
        self._is_success = is_success

        # Set up entry fade
        self.setWindowOpacity(0.0)
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(250)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(0.96)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._fade_anim.start()

        # Auto-fade out timer
        self._close_timer = QTimer(self)
        self._close_timer.setInterval(2800) # stays visible for 2.8 seconds
        self._close_timer.setSingleShot(True)
        self._close_timer.timeout.connect(self._fade_out)
        self._close_timer.start()

    def _fade_out(self) -> None:
        self._fade_anim.stop()
        self._fade_anim.setDuration(350)
        self._fade_anim.setStartValue(self.windowOpacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.InQuad)
        self._fade_anim.finished.connect(self.close)
        self._fade_anim.start()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Glassmorphic card background
        bg_rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        
        # Deep dark back
        bg_grad = QLinearGradient(0, 0, 0, self.height())
        bg_grad.setColorAt(0.0, QColor(10, 8, 18, 240))
        bg_grad.setColorAt(1.0, QColor(6, 5, 12, 245))
        
        # Border glow: Green for success, Violet for warning/already running
        border_color = QColor(16, 185, 129, 140) if self._is_success else QColor(139, 92, 246, 140)
        border_pen = QPen(border_color, 1.2)
        
        painter.setBrush(QBrush(bg_grad))
        painter.setPen(border_pen)
        painter.drawRoundedRect(bg_rect, 10, 10)

        # Draw Badge/Icon
        icon_rect = QRect(18, 19, 30, 30)
        painter.setPen(Qt.PenStyle.NoPen)
        if self._is_success:
            painter.setBrush(QBrush(QColor(16, 185, 129, 30)))
            painter.drawEllipse(icon_rect)
            
            # Green checkmark symbol
            painter.setPen(QPen(QColor(16, 185, 129), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawLine(28, 34, 32, 38)
            painter.drawLine(32, 38, 39, 29)
        else:
            painter.setBrush(QBrush(QColor(139, 92, 246, 30)))
            painter.drawEllipse(icon_rect)
            
            # Violet info dot symbol
            painter.setPen(QPen(QColor(167, 139, 250), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawPoint(33, 27)
            painter.drawLine(33, 31, 33, 37)

        # Message Text
        text_font = QFont("Segoe UI", 10.5, QFont.Weight.Medium)
        painter.setFont(text_font)
        painter.setPen(QColor("#f3f4f6"))
        
        text_rect = QRect(62, 0, self.width() - 80, self.height())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._message)

# ---------------------------------------------------------------------------
# Status Dashboard Window
# ---------------------------------------------------------------------------

class StatusWindow(QWidget):
    """Modern borderless draggable status dashboard window."""
    
    restart_requested = Signal()

    def __init__(self, cfg_host: str, cfg_port: int) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(380, 290)

        # Center on primary screen initially
        screen = QGuiApplication.primaryScreen().geometry()
        self.move((screen.width() - self.width()) // 2, (screen.height() - self.height()) // 2)

        self._cfg_host = cfg_host
        self._cfg_port = cfg_port

        # Pulse heartbeat state for active dot
        self._pulse_alpha = 255
        self._pulse_growing = False
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(45)
        self._pulse_timer.timeout.connect(self._update_pulse)
        self._pulse_timer.start()

        # Drag helper states
        self._drag_pos = None

        self._init_ui()

    def _update_pulse(self) -> None:
        if self._pulse_growing:
            self._pulse_alpha += 12
            if self._pulse_alpha >= 255:
                self._pulse_alpha = 255
                self._pulse_growing = False
        else:
            self._pulse_alpha -= 12
            if self._pulse_alpha <= 70:
                self._pulse_alpha = 70
                self._pulse_growing = True
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            # Only drag from top header region (y < 50)
            if event.position().y() < 50:
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        
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
        """)

        frame = QFrame(self)
        frame.setObjectName("mainFrame")
        frame.setStyleSheet("QFrame#mainFrame { background: transparent; }")
        layout.addWidget(frame)

    def show_activated(self) -> None:
        """Single source of truth to restore, show, activate, and raise the window."""
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event) -> None:
        """Override close event to hide the window instead of closing it."""
        event.ignore()
        self.hide()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw card background
        bg_rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        
        # Custom dark base gradient
        bg_grad = QLinearGradient(0, 0, 0, self.height())
        bg_grad.setColorAt(0.0, QColor(14, 12, 24, 245))
        bg_grad.setColorAt(1.0, QColor(8, 7, 14, 250))
        
        painter.setBrush(QBrush(bg_grad))
        painter.setPen(QPen(QColor(139, 92, 246, 80), 1.5))
        painter.drawRoundedRect(bg_rect, 12, 12)

        # Title bar divider line
        painter.setPen(QPen(QColor(255, 255, 255, 12), 1.0))
        painter.drawLine(2, 48, self.width() - 2, 48)

        # Logo in title bar (left aligned)
        logo_path = get_interact_logo_path(0.35)
        bounds = logo_path.boundingRect()
        painter.save()
        painter.translate(18, 24 - bounds.center().y())
        painter.setBrush(QBrush(QColor("#a78bfa")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(logo_path)
        painter.restore()

        # Title Text
        painter.setFont(QFont("Segoe UI", 11.5, QFont.Weight.DemiBold))
        painter.setPen(QColor("#f3f4f6"))
        painter.drawText(46, 16, 200, 24, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "InterAct Collaboration")

        # Dashboard status cards
        card_x = 20
        card_w = self.width() - 40
        card_r = 8
        
        # 1. State card
        painter.setPen(QPen(QColor(255, 255, 255, 8), 1.0))
        painter.setBrush(QBrush(QColor(255, 255, 255, 6)))
        painter.drawRoundedRect(card_x, 65, card_w, 52, card_r, card_r)
        
        painter.setFont(QFont("Segoe UI", 9.5))
        painter.setPen(QColor("#9ca3af"))
        painter.drawText(card_x + 15, 65 + 10, 100, 16, Qt.AlignmentFlag.AlignLeft, "Agent Status")
        
        painter.setFont(QFont("Segoe UI", 10.5, QFont.Weight.Bold))
        painter.setPen(QColor("#f3f4f6"))
        painter.drawText(card_x + 15, 65 + 26, 100, 20, Qt.AlignmentFlag.AlignLeft, "RUNNING")
        
        # Pulsing active green dot
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(16, 185, 129, int(self._pulse_alpha * 0.3))))
        painter.drawEllipse(QPointF(self.width() - 36, 65 + 26), 9.0, 9.0)
        painter.setBrush(QBrush(QColor(16, 185, 129)))
        painter.drawEllipse(QPointF(self.width() - 36, 65 + 26), 4.5, 4.5)

        # 2. Services card
        painter.setPen(QPen(QColor(255, 255, 255, 8), 1.0))
        painter.setBrush(QBrush(QColor(255, 255, 255, 6)))
        painter.drawRoundedRect(card_x, 128, card_w, 88, card_r, card_r)

        painter.setFont(QFont("Segoe UI", 9))
        painter.setPen(QColor("#9ca3af"))
        painter.drawText(card_x + 15, 128 + 12, 120, 16, Qt.AlignmentFlag.AlignLeft, "WebSocket Server")
        painter.drawText(card_x + 15, 128 + 48, 120, 16, Qt.AlignmentFlag.AlignLeft, "Collaboration Overlay")

        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
        painter.setPen(QColor("#a78bfa"))
        painter.drawText(card_x + 15, 128 + 26, 250, 18, Qt.AlignmentFlag.AlignLeft, f"ws://{self._cfg_host}:{self._cfg_port}")
        painter.setPen(QColor("#f3f4f6"))
        painter.drawText(card_x + 15, 128 + 62, 250, 18, Qt.AlignmentFlag.AlignLeft, "Active (all monitors)")

        # Version stamp (bottom left corner)
        from src.agent_version import AGENT_VERSION
        painter.setFont(QFont("Segoe UI", 8.5))
        painter.setPen(QColor("#6b7280"))
        painter.drawText(22, self.height() - 38, 150, 20, Qt.AlignmentFlag.AlignLeft, f"v{AGENT_VERSION}")

        # Close button hover area decoration
        painter.setFont(QFont("Segoe UI", 12))
        painter.setPen(QColor("#9ca3af"))
        painter.drawText(self.width() - 32, 14, 20, 20, Qt.AlignmentFlag.AlignCenter, "×")


class InteractiveStatusWindow(StatusWindow):
    """Extends StatusWindow to include interactive QPushButton elements."""

    def __init__(self, cfg_host: str, cfg_port: int) -> None:
        super().__init__(cfg_host, cfg_port)

        # Close button in top-right corner
        self.close_btn = QPushButton("×", self)
        self.close_btn.setObjectName("closeIconBtn")
        self.close_btn.setGeometry(self.width() - 34, 10, 24, 24)
        self.close_btn.clicked.connect(self.hide)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        # Action Buttons at the bottom
        btn_y = self.height() - 44
        
        self.restart_btn = QPushButton("Restart Agent", self)
        self.restart_btn.setObjectName("secondaryBtn")
        self.restart_btn.setGeometry(self.width() - 225, btn_y, 100, 28)
        self.restart_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.restart_btn.clicked.connect(self.restart_requested.emit)

        self.quit_btn = QPushButton("Quit Agent", self)
        self.quit_btn.setObjectName("primaryBtn")
        self.quit_btn.setGeometry(self.width() - 115, btn_y, 95, 28)
        self.quit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.quit_btn.clicked.connect(QApplication.quit)

# ---------------------------------------------------------------------------
# Tray Icon Manager
# ---------------------------------------------------------------------------

class TrayManager(QObject):
    """Manages the QSystemTrayIcon, its menu actions, and dashboard links."""

    def __init__(self, parent_app: QApplication, agent_app: Any) -> None:
        super().__init__()
        self._app = parent_app
        self._agent_app = agent_app
        self._status_window = agent_app.status_window

        self._tray_icon = QSystemTrayIcon(create_tray_icon(), self)
        self._tray_icon.setToolTip("InterAct Collaboration Agent")

        self._init_menu()
        
        self._tray_icon.activated.connect(self._on_activated)
        self._tray_icon.show()

    def _init_menu(self) -> None:
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #0e0d16;
                color: #f3f4f6;
                border: 1px solid #312e81;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                font-family: 'Segoe UI', Arial;
                font-size: 11px;
                padding: 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #4f46e5;
                color: #ffffff;
            }
            QMenu::item:disabled {
                color: #6b7280;
            }
        """)

        # Title (disabled)
        title_action = menu.addAction("InterAct Desktop Agent")
        title_action.setEnabled(False)
        font = title_action.font()
        font.setBold(True)
        title_action.setFont(font)

        # Status (disabled)
        status_action = menu.addAction("Status: Running")
        status_action.setEnabled(False)

        menu.addSeparator()

        # Open (bold)
        open_action = menu.addAction("Open")
        font = open_action.font()
        font.setBold(True)
        open_action.setFont(font)
        open_action.triggered.connect(self._open_or_toggle_status)

        # Check for Updates
        update_action = menu.addAction("Check for Updates")
        update_action.triggered.connect(self._check_for_updates)

        # Restart Agent
        restart_action = menu.addAction("Restart Agent")
        if hasattr(self._status_window, "restart_requested"):
            restart_action.triggered.connect(self._status_window.restart_requested.emit)

        # Exit
        exit_action = menu.addAction("Exit")
        exit_action.triggered.connect(self._app.quit)

        self._tray_icon.setContextMenu(menu)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self._open_or_toggle_status()

    def _open_or_toggle_status(self) -> None:
        window = self._status_window
        if not window:
            return
        
        # Toggle: hide if visible, not minimized, and focused; otherwise show/activate
        if window.isVisible() and not window.isMinimized() and window.isActiveWindow():
            window.hide()
        else:
            window.show_activated()

    def _check_for_updates(self) -> None:
        if hasattr(self._agent_app, "update_manager") and self._agent_app.update_manager:
            self._agent_app.update_manager.check_for_updates(interactive=True)

    def cleanup(self) -> None:
        """Clean up resources and hide the tray icon to prevent it from lingering."""
        self._tray_icon.hide()

    def show_message(self, title: str, message: str) -> None:
        """Trigger native system tray balloon message."""
        self._tray_icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 3000)
