import os
from PySide6.QtWidgets import QLabel, QSizePolicy, QCheckBox
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

def setup_format_toggle(app, config_manager):
    """Set up format toggle UI elements and connect signals"""
    # Get UI elements
    format_toggle = app.findChild(QCheckBox, "formatToggle")
    format_label_png = app.findChild(QLabel, "formatLabel")
    format_label_jpg = app.findChild(QLabel, "formatLabel2")
    
    if not all([format_toggle, format_label_png, format_label_jpg]):
        logger.peringatan("Format toggle UI elements not found")
        return
    
    # Set toggle state based on config
    current_format = config_manager.get_output_format()
    format_toggle.setChecked(current_format == "jpg")
    
    # Update label colors based on initial state
    update_format_labels(format_label_png, format_label_jpg, current_format == "jpg")
    
    # Connect toggle signal
    format_toggle.stateChanged.connect(
        lambda state: on_format_toggle_changed(state, format_label_png, format_label_jpg, config_manager)
    )
    
    return format_toggle, format_label_png, format_label_jpg

def update_format_labels(label_png, label_jpg, is_jpg):
    """Update format label colors based on the selected format"""
    if is_jpg:
        # JPG mode - JPG is highlighted and PNG is dimmed
        if label_png:
            label_png.setStyleSheet("color: rgba(88, 29, 239, 0.5);")
        if label_jpg:
            label_jpg.setStyleSheet("color: rgba(52, 152, 219, 1.0);")
    else:
        # PNG mode - PNG is highlighted and JPG is dimmed
        if label_png:
            label_png.setStyleSheet("color: rgba(88, 29, 239, 1.0);")
        if label_jpg:
            label_jpg.setStyleSheet("color: rgba(52, 152, 219, 0.5);")

def on_format_toggle_changed(state, label_png, label_jpg, config_manager):
    """Handle format toggle state change"""
    # Qt.Checked is 2, so let's explicitly check against that
    is_jpg = (state == 2)  # Qt.Checked is 2 in PySide6
    
    # Debug output to see what's happening
    print(f"Toggle state changed: state={state}, is_jpg={is_jpg}")
    
    # Update the config with the new format
    config_manager.set_output_format("jpg" if is_jpg else "png")
    
    # Update label colors
    update_format_labels(label_png, label_jpg, is_jpg)
    
    # Log the format change
    logger.info(f"Output format changed to: {'JPG' if is_jpg else 'PNG'}")
