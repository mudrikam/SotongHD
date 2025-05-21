import os
import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget
from PySide6.QtUiTools import QUiLoader
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtCore import Qt, QRect, QPoint

class BackgroundWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.bg_pixmap = None
        self.setAttribute(Qt.WA_StyledBackground, False)
        
    def set_background(self, bg_path):
        if os.path.exists(bg_path):
            self.bg_pixmap = QPixmap(bg_path)
            self.update()
        
    def paintEvent(self, event):
        if self.bg_pixmap:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            
            # Calculate position to center the image
            scaled_pixmap = self.bg_pixmap.scaled(
                self.width() * 0.8,  # Scale to 80% of window width
                self.height() * 0.8,  # Scale to 80% of window height
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            
            # Center the image
            x = (self.width() - scaled_pixmap.width()) // 2
            y = (self.height() - scaled_pixmap.height()) // 2
            
            # Draw the image at the calculated position
            painter.drawPixmap(x, y, scaled_pixmap)

class SotongHDApp(QMainWindow):
    def __init__(self, base_dir, icon_path=None):
        super().__init__()
        
        # Store the base directory
        self.base_dir = base_dir
        
        # Set icon if provided
        if icon_path and os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            # Set application-wide icon
            QApplication.setWindowIcon(QIcon(icon_path))
        
        # Load the UI
        ui_file = os.path.join(base_dir, "App", "main_window.ui")
        loader = QUiLoader()
        self.ui = loader.load(ui_file)
        
        # Set window properties from UI
        self.setGeometry(self.ui.geometry())
        self.setWindowTitle(self.ui.windowTitle())
        
        # Center the window on the screen
        self.center_on_screen()
        
        # Create a background widget and set it as central
        self.bg_widget = BackgroundWidget(self)
        self.setCentralWidget(self.bg_widget)
        
        # Get the labels from UI and reparent them to our background widget
        self.titleLabel = self.ui.findChild(QWidget, "titleLabel")
        self.subtitleLabel = self.ui.findChild(QWidget, "subtitleLabel")
        
        if self.titleLabel:
            # Make sure the label has correct parent and stays on top
            self.titleLabel.setParent(self.bg_widget)
            # Position the label in the center top area
            self.titleLabel.setGeometry(0, self.height() // 4, self.width(), 50)
            self.titleLabel.setAlignment(Qt.AlignCenter)
            # Make sure it's visible
            self.titleLabel.show()
            self.titleLabel.raise_()
            
        if self.subtitleLabel:
            # Make sure the subtitle has correct parent and stays on top
            self.subtitleLabel.setParent(self.bg_widget)
            # Position the subtitle below the title
            subtitle_y = self.height() // 4 + 60 if self.titleLabel else self.height() // 3
            self.subtitleLabel.setGeometry(0, subtitle_y, self.width(), 100)
            self.subtitleLabel.setAlignment(Qt.AlignCenter)
            # Make sure it's visible
            self.subtitleLabel.show()
            self.subtitleLabel.raise_()
        
        # Set background image
        bg_path = os.path.join(base_dir, "App", "sotong_bg.png")
        if os.path.exists(bg_path):
            self.bg_widget.set_background(bg_path)
        else:
            print(f"Warning: Background image not found at {bg_path}")
            
        # Make sure the label stays on top when window is resized
        self.bg_widget.installEventFilter(self)
        
        # Show the main window
        self.show()
    
    def center_on_screen(self):
        """Center the window on the screen."""
        screen_geometry = QApplication.primaryScreen().geometry()
        window_geometry = self.geometry()
        
        x = (screen_geometry.width() - window_geometry.width()) // 2
        y = (screen_geometry.height() - window_geometry.height()) // 2
        
        self.move(x, y)
    
    def eventFilter(self, obj, event):
        if obj == self.bg_widget and event.type() == 14 and hasattr(self, 'titleLabel'):  # 14 is the value for Resize event
            # Keep labels positioned correctly when window is resized
            if hasattr(self, 'titleLabel') and self.titleLabel:
                self.titleLabel.setGeometry(0, self.height() // 4, self.bg_widget.width(), 50)
            
            if hasattr(self, 'subtitleLabel') and self.subtitleLabel:
                subtitle_y = self.height() // 4 + 60 if hasattr(self, 'titleLabel') and self.titleLabel else self.height() // 3
                self.subtitleLabel.setGeometry(0, subtitle_y, self.bg_widget.width(), 100)
                
        return super().eventFilter(obj, event)

def run_app(base_dir, icon_path=None):
    # Create Qt application
    app = QApplication(sys.argv)
    
    # Create main window
    window = SotongHDApp(base_dir, icon_path)
    
    # Start the event loop
    sys.exit(app.exec())

if __name__ == "__main__":
    # If run directly (for testing), use the current directory as base
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    run_app(base_dir)
