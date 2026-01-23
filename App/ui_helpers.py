import os
from PySide6.QtWidgets import QLabel, QSizePolicy, QCheckBox, QPushButton
from PySide6.QtGui import QPixmap, QPainter, QPainterPath, QIcon
from PySide6.QtCore import Qt, QSize, QRectF
from .logger import logger

class ScalableImageLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.original_pixmap = None
        self.image_path = None
        self.rounded_pixmap = None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        self.setStyleSheet("""
            QLabel {
                padding: 5px;
                background-color: transparent;
            }
        """)
        
    def setImagePath(self, path):
        if not os.path.exists(path):
            return False
        self.image_path = str(path)
        self.original_pixmap = QPixmap(self.image_path)
        self.updatePixmap()
        return not self.original_pixmap.isNull()
        
    def updatePixmap(self):
        if self.original_pixmap and not self.original_pixmap.isNull():
            width = max(10, self.width() - 24)
            height = max(10, self.height() - 24)
            
            self.scaled_pixmap = self.original_pixmap.scaled(
                width, 
                height,
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
            
            self.setMinimumSize(100, 100)
            self.update()
    
    def paintEvent(self, event):
        super().paintEvent(event)
        
        if hasattr(self, 'scaled_pixmap') and self.scaled_pixmap and not self.scaled_pixmap.isNull():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            
            pixmap_rect = self.scaled_pixmap.rect()
            x = (self.width() - pixmap_rect.width()) // 2
            y = (self.height() - pixmap_rect.height()) // 2
            
            radius = 20
            path = QPainterPath()
            path.addRoundedRect(
                QRectF(x, y, pixmap_rect.width(), pixmap_rect.height()),
                radius, radius
            )
            
            painter.setClipPath(path)
            
            painter.drawPixmap(x, y, self.scaled_pixmap)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.updatePixmap()
        
    def sizeHint(self):
        return QSize(200, 200)
        
    def minimumSizeHint(self):
        return QSize(10, 10)

def center_window_on_screen(window):
    from PySide6.QtWidgets import QApplication
    screen_geometry = QApplication.primaryScreen().geometry()
    window_geometry = window.geometry()
    
    x = (screen_geometry.width() - window_geometry.width()) // 2
    y = (screen_geometry.height() - window_geometry.height()) // 2
    
    window.move(x, y)

def setup_drag_drop_style(frame, highlighted=False):
    if not frame:
        return
        
    if highlighted:
        frame.setStyleSheet("""
            QFrame#dropFrame {
                border: 2px dashed rgba(88, 29, 239, 0.5);
                border-radius: 15px;
                background-color: rgba(88, 29, 239, 0.15);
            }
        """)
    else:
        frame.setStyleSheet("""
            QFrame#dropFrame {
                border: 2px dashed rgba(88, 29, 239, 0.2);
                border-radius: 15px;
                background-color: rgba(88, 29, 239, 0.08);
            }
        """)

def setup_format_toggle(app, config_manager):
    format_toggle = app.findChild(QPushButton, "formatToggle")
    
    if not format_toggle:
        logger.peringatan("Format toggle UI element not found")
        return
    
    format_toggle.setCheckable(True)
    current_format = config_manager.get_output_format()
    is_jpg = current_format == "jpg"
    format_toggle.setChecked(is_jpg)
    format_toggle.setText("JPG" if is_jpg else "PNG")
    
    format_toggle.setStyleSheet("""
        QPushButton {
            border-radius: 15px;
            border: none;
            width: 60px;
            height: 30px;
            background-color: rgb(88, 29, 239);
            color: white;
            font-weight: bold;
            font-size: 12px;
        }
        QPushButton:checked {
            background-color: rgb(192, 57, 43);
        }
    """)
    format_toggle.toggled.connect(
        lambda checked: on_format_toggle_changed(checked, format_toggle, config_manager)
    )
    
    return format_toggle

def on_format_toggle_changed(checked, format_toggle, config_manager):
    is_jpg = checked
    config_manager.set_output_format("jpg" if is_jpg else "png")
    format_toggle.setText("JPG" if is_jpg else "PNG")
    logger.info(f"Output format changed to: {'JPG' if is_jpg else 'PNG'}")

def set_application_icon(app, icon_path):
    if icon_path and os.path.exists(icon_path):
        icon_label = app.findChild(QLabel, "iconLabel")
        
        if icon_label:
            try:
                if icon_path.lower().endswith('.ico'):
                    icon = QIcon(icon_path)
                    available_sizes = icon.availableSizes()
                    
                    if available_sizes:
                        largest_size = max(available_sizes, key=lambda s: s.width() * s.height())
                        pixmap = icon.pixmap(largest_size)
                    else:
                        pixmap = icon.pixmap(QSize(256, 256))
                else:
                    pixmap = QPixmap(icon_path)
                
                if not pixmap.isNull():
                    display_size = 128
                    scaled_pixmap = pixmap.scaled(
                        display_size, display_size,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )
                    
                    icon_label.setPixmap(scaled_pixmap)
                    icon_label.setAlignment(Qt.AlignCenter)
                    icon_label.setMinimumSize(display_size, display_size)
                    return True
                else:
                    logger.peringatan(f"Gagal memuat icon - pixmap null: {icon_path}")
            except Exception as e:
                logger.kesalahan(f"Error saat memuat ikon aplikasi", str(e))
    
    return False
