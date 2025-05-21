import os
import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QMessageBox, QProgressBar, QVBoxLayout
from PySide6.QtUiTools import QUiLoader
from PySide6.QtGui import QIcon, QPixmap, QPainter, QImageReader, QDragEnterEvent, QDropEvent
from PySide6.QtCore import Qt, QRect, QPoint, QMimeData, QUrl
from pathlib import Path

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
        
        # Set up drag and drop support
        self.setAcceptDrops(True)
        
        # Get the drop frame and labels from UI and reparent them to our background widget
        self.dropFrame = self.ui.findChild(QWidget, "dropFrame")
        self.titleLabel = self.ui.findChild(QWidget, "titleLabel")
        self.subtitleLabel = self.ui.findChild(QWidget, "subtitleLabel")
          # Current displayed image (for processing)
        self.current_image = None
        
        # Create progress bar
        self.progress_bar = QProgressBar(self.bg_widget)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Ready")
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 10px;
                background-color: rgba(161, 161, 161, 0.08);
                text-align: center;
                color: #333;
                font-weight: bold;
                margin: 0px;
                padding: 0px;
                height: 30px;
            }
            QProgressBar::chunk {
                background-color: #5720e3;
                border-radius: 10px;
            }
        """)
        self.progress_bar.show()  # Initially visible with "Ready"
        
        if self.dropFrame:
            self.dropFrame.setParent(self.bg_widget)
            
            # Define margins for dynamic sizing (padding from window edges)
            self.margin = 20  # 20px padding from each side of the window
            
            # Set initial geometry with margins
            self.update_drop_frame_geometry()
              # Apply the theme style
            self.dropFrame.setStyleSheet("""
                QFrame#dropFrame {
                    border: 2px dashed rgba(88, 29, 239, 0.2);
                    border-radius: 15px;
                    background-color: rgba(88, 29, 239, 0.08);
                }
            """)
            
            self.dropFrame.show()
            self.dropFrame.raise_()
            
        if self.titleLabel:
            # Make sure the label has correct parent and stays on top
            self.titleLabel.setParent(self.dropFrame)
            # Position the label in the center top area
            self.titleLabel.setGeometry(0, 50, self.dropFrame.width(), 50)
            self.titleLabel.setAlignment(Qt.AlignCenter)
            # Make sure it's visible
            self.titleLabel.show()
            self.titleLabel.raise_()
            
        if self.subtitleLabel:
            # Make sure the subtitle has correct parent and stays on top
            self.subtitleLabel.setParent(self.dropFrame)
            # Position the subtitle below the title
            subtitle_y = 110
            self.subtitleLabel.setGeometry(50, subtitle_y, self.dropFrame.width() - 100, 100)
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
            
        # Make sure the components stay properly positioned when window is resized
        self.bg_widget.installEventFilter(self)
          # Show the main window
        self.show()
        
        # Update progress bar position
        self.update_progress_bar_position()
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle when dragged items enter the window"""
        # Check if the dragged data has URLs (file paths)
        if event.mimeData().hasUrls():
            # Check if at least one URL is an image file
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if self.is_image_file(file_path):
                    event.acceptProposedAction()
                    if self.dropFrame:
                        self.dropFrame.setStyleSheet("""
                            QFrame#dropFrame {
                                border: 2px dashed rgba(88, 29, 239, 0.5);
                                border-radius: 15px;
                                background-color: rgba(88, 29, 239, 0.15);
                            }
                        """)
                    return
        event.ignore()    
    def dragLeaveEvent(self, event):
        """Handle when dragged items leave the window"""
        if self.dropFrame:
            self.dropFrame.setStyleSheet("""
                QFrame#dropFrame {
                    border: 2px dashed rgba(88, 29, 239, 0.2);
                    border-radius: 15px;
                    background-color: rgba(88, 29, 239, 0.08);
                }
            """)
        
    def dragMoveEvent(self, event):
        """Handle when dragged items move within the window"""
        # We already checked the mime data in dragEnterEvent, so just accept
        if event.mimeData().hasUrls():
            event.acceptProposedAction()    
    def dropEvent(self, event: QDropEvent):
        """Handle when items are dropped into the window"""
        # Reset the dropFrame style
        if self.dropFrame:
            self.dropFrame.setStyleSheet("""
                QFrame#dropFrame {
                    border: 2px dashed rgba(88, 29, 239, 0.2);
                    border-radius: 15px;
                    background-color: rgba(88, 29, 239, 0.08);
                }
            """)
        
        # Process the dropped files
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            
            # Get the first valid image file from the dropped URLs
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if self.is_image_file(file_path):
                    self.process_image(file_path)
                    break
    
    def is_image_file(self, file_path):
        """Check if the file is a valid image that can be loaded"""
        if not os.path.isfile(file_path):
            return False
            
        # Check if it's a supported image format
        reader = QImageReader(file_path)
        return reader.canRead()
    
    def process_image(self, image_path):
        """Process the dropped image"""
        try:
            # Load the image
            pixmap = QPixmap(image_path)
            if pixmap.isNull():
                QMessageBox.warning(self, "Image Error", f"Cannot load image: {image_path}")
                return
                
            self.current_image = pixmap
            
            # Show progress bar for demonstration
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("Processing image... %p%")
            self.progress_bar.show()
            
            # Here you would implement actual processing with progress updates
            # For demo, we'll just simulate progress
            QApplication.processEvents()
            for i in range(1, 101):
                self.progress_bar.setValue(i)
                QApplication.processEvents()
                # Simulate processing time
                import time
                time.sleep(0.02)  # Add a small delay to see the progress
            
            # Set to Ready when done but keep visible
            self.progress_bar.setValue(100)
            self.progress_bar.setFormat("Done")
            
            # Show a message with the file path
            file_name = Path(image_path).name
            QMessageBox.information(
                self, 
                "Image Loaded", 
                f"Image loaded successfully: {file_name}\n\nSize: {pixmap.width()}x{pixmap.height()} pixels"
            )
            
            # Reset progress bar to Ready state after processing
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("Ready")
            
        except Exception as e:
            self.progress_bar.setFormat("Error")
            QMessageBox.critical(self, "Error", f"An error occurred processing the image: {str(e)}")
    
    def update_drop_frame_geometry(self):
        """Update the drop frame geometry to be dynamic with window size."""
        if self.dropFrame:
            # Calculate new size with margins on all sides, but leave space for progress bar
            progress_bar_height = 40  # Height of progress bar + some margin
            width = self.width() - (self.margin * 2)
            height = self.height() - (self.margin * 2) - progress_bar_height
            
            # Set the geometry with margins
            self.dropFrame.setGeometry(
                self.margin,  # X position (left margin)
                self.margin,  # Y position (top margin)
                width,        # Width (window width minus left and right margins)
                height        # Height (window height minus margins and progress bar space)
            )
            
            # Update label positions if needed
            if hasattr(self, 'titleLabel') and self.titleLabel:
                self.titleLabel.setGeometry(0, 50, self.dropFrame.width(), 50)
            
            if hasattr(self, 'subtitleLabel') and self.subtitleLabel:
                self.subtitleLabel.setGeometry(50, 110, self.dropFrame.width() - 100, 100)
                
            # Update progress bar position - now directly below the drop area
            self.update_progress_bar_position()
    
    def update_progress_bar_position(self):
        """Position the progress bar below the drop area."""
        progress_height = 30
        
        if self.dropFrame:
            self.progress_bar.setGeometry(
                self.margin,  # X position (same as drop frame)
                self.dropFrame.y() + self.dropFrame.height() + 10,  # Y position (just below drop frame)
                self.width() - (self.margin * 2),  # Width (same as drop frame)
                progress_height  # Height
            )
        else:
            # Fallback if dropFrame doesn't exist
            self.progress_bar.setGeometry(
                self.margin,
                self.height() - progress_height - 10,
                self.width() - (self.margin * 2),
                progress_height
            )
        
        # Make sure progress bar is visible with initial "Ready" message
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Ready")
        self.progress_bar.show()
    
    def center_on_screen(self):
        """Center the window on the screen."""
        screen_geometry = QApplication.primaryScreen().geometry()
        window_geometry = self.geometry()
        
        x = (screen_geometry.width() - window_geometry.width()) // 2
        y = (screen_geometry.height() - window_geometry.height()) // 2
        
        self.move(x, y)
    
    def eventFilter(self, obj, event):
        if obj == self.bg_widget and event.type() == 14:  # 14 is the value for Resize event
            # Keep components positioned correctly when window is resized
            if hasattr(self, 'dropFrame') and self.dropFrame:
                self.update_drop_frame_geometry()
                self.update_progress_bar_position()
                
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
