import os
from PySide6.QtWidgets import QLabel, QSizePolicy
from PySide6.QtGui import QPixmap, QPainter, QPainterPath
from PySide6.QtCore import Qt, QSize, QRectF
from .logger import logger

class ScalableImageLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.original_pixmap = None
        self.image_path = None
        self.rounded_pixmap = None
        # Set size policy to allow the widget to shrink
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Remove background styling, only keep minimal padding
        self.setStyleSheet("""
            QLabel {
                padding: 5px;
                background-color: transparent;
            }
        """)
        
    def setImagePath(self, path):
        """Menyimpan path gambar dan memuat pixmap original"""
        if not os.path.exists(path):
            return False
            
        # Ensure path is a string to avoid any type issues
        self.image_path = str(path)
        self.original_pixmap = QPixmap(self.image_path)
        self.updatePixmap()
        return not self.original_pixmap.isNull()
        
    def updatePixmap(self):
        """Menyesuaikan ukuran gambar sesuai dengan ukuran label"""
        if self.original_pixmap and not self.original_pixmap.isNull():
            # Handle potential zero-sized widget
            width = max(10, self.width() - 24)  # Account for padding and border
            height = max(10, self.height() - 24)
            
            # Create a scaled version of the pixmap
            self.scaled_pixmap = self.original_pixmap.scaled(
                width, 
                height,
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
            
            # Don't set the pixmap directly - we'll draw it in paintEvent
            self.setMinimumSize(100, 100)
            self.update()  # Force a repaint
    
    def paintEvent(self, event):
        """Override paint event to draw rounded image"""
        super().paintEvent(event)
        
        if hasattr(self, 'scaled_pixmap') and self.scaled_pixmap and not self.scaled_pixmap.isNull():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            
            # Calculate centered position
            pixmap_rect = self.scaled_pixmap.rect()
            x = (self.width() - pixmap_rect.width()) // 2
            y = (self.height() - pixmap_rect.height()) // 2
            
            # Create a rounded rect path with stronger radius
            radius = 20  # Increased border radius for the image
            path = QPainterPath()
            path.addRoundedRect(
                QRectF(x, y, pixmap_rect.width(), pixmap_rect.height()),
                radius, radius
            )
            
            # Set the clipping path to the rounded rectangle
            painter.setClipPath(path)
            
            # Draw the pixmap inside the clipping path
            painter.drawPixmap(x, y, self.scaled_pixmap)
    
    def resizeEvent(self, event):
        """Event yang terpanggil saat widget di-resize"""
        super().resizeEvent(event)
        self.updatePixmap()
        
    # Override size hint methods to allow widget to shrink
    def sizeHint(self):
        return QSize(200, 200)
        
    def minimumSizeHint(self):
        return QSize(10, 10)

def center_window_on_screen(window):
    """Center a window on the screen."""
    from PySide6.QtWidgets import QApplication
    screen_geometry = QApplication.primaryScreen().geometry()
    window_geometry = window.geometry()
    
    x = (screen_geometry.width() - window_geometry.width()) // 2
    y = (screen_geometry.height() - window_geometry.height()) // 2
    
    window.move(x, y)

def setup_drag_drop_style(frame, highlighted=False):
    """Set the style for the drag and drop frame"""
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
