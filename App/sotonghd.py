import os
import sys
import time
from datetime import datetime, timedelta
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QMessageBox, QProgressBar, 
                              QVBoxLayout, QDialog, QLabel, QTextBrowser, QPushButton, QFileDialog,
                              QHBoxLayout, QGridLayout, QScrollArea)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtGui import QIcon, QPixmap, QPainter, QImageReader, QDragEnterEvent, QDropEvent
from PySide6.QtCore import Qt, QRect, QPoint, QMimeData, QUrl, Signal, QObject
from pathlib import Path
from .background_process import ImageProcessor

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


class StatsDialog(QDialog):
    """Dialog untuk menampilkan statistik pemrosesan."""
    
    def __init__(self, parent=None, stats=None):
        super().__init__(parent)
        self.stats = stats
        self.initUI()
        
    def initUI(self):
        self.setWindowTitle("Statistik SotongHD")
        self.setMinimumSize(600, 400)
        self.setWindowIcon(self.parent().windowIcon())
        
        # Layout utama
        layout = QVBoxLayout(self)
        
        # Header
        header_layout = QHBoxLayout()
        icon_label = QLabel()
        if self.parent() and self.parent().windowIcon():
            icon = self.parent().windowIcon()
            pixmap = icon.pixmap(64, 64)
            icon_label.setPixmap(pixmap)
        header_layout.addWidget(icon_label)
        
        header_text = QLabel("<h1>SotongHD Report</h1>")
        header_text.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(header_text, 1)
        
        layout.addLayout(header_layout)
        
        # Stats grid
        grid_layout = QGridLayout()
        
        if self.stats:
            # Total processed
            grid_layout.addWidget(QLabel("<b>Total Gambar Berhasil:</b>"), 0, 0)
            grid_layout.addWidget(QLabel(f"{self.stats['total_processed']}"), 0, 1)
            
            # Total failed
            grid_layout.addWidget(QLabel("<b>Total Gambar Gagal:</b>"), 1, 0)
            grid_layout.addWidget(QLabel(f"{self.stats['total_failed']}"), 1, 1)
            
            # Total files
            total_files = self.stats['total_processed'] + self.stats['total_failed']
            grid_layout.addWidget(QLabel("<b>Total File:</b>"), 2, 0)
            grid_layout.addWidget(QLabel(f"{total_files}"), 2, 1)
            
            # Time info
            if self.stats['start_time'] and self.stats['end_time']:
                start_time = self.stats['start_time'].strftime("%H:%M:%S")
                end_time = self.stats['end_time'].strftime("%H:%M:%S")
                
                grid_layout.addWidget(QLabel("<b>Waktu Mulai:</b>"), 3, 0)
                grid_layout.addWidget(QLabel(start_time), 3, 1)
                
                grid_layout.addWidget(QLabel("<b>Waktu Selesai:</b>"), 4, 0)
                grid_layout.addWidget(QLabel(end_time), 4, 1)
                
                # Duration
                duration = timedelta(seconds=int(self.stats['total_duration']))
                grid_layout.addWidget(QLabel("<b>Durasi:</b>"), 5, 0)
                grid_layout.addWidget(QLabel(str(duration)), 5, 1)
        else:
            grid_layout.addWidget(QLabel("Tidak ada data statistik."), 0, 0, 1, 2)
            
        layout.addLayout(grid_layout)
        
        # Folder list
        if self.stats and 'processed_folders' in self.stats and self.stats['processed_folders']:
            layout.addWidget(QLabel("<b>Folder yang Diproses:</b>"))
            
            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(True)
            
            folder_widget = QWidget()
            folder_layout = QVBoxLayout(folder_widget)
            
            for folder in self.stats['processed_folders']:
                folder_layout.addWidget(QLabel(folder))
                
            scroll_area.setWidget(folder_widget)
            layout.addWidget(scroll_area)
        
        # Close button
        btn_close = QPushButton("Tutup")
        btn_close.clicked.connect(self.accept)
        
        layout.addWidget(btn_close)
        
        self.setLayout(layout)

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
        
        # Inisialisasi image processor
        chromedriver_path = os.path.join(base_dir, "driver", "chromedriver.exe")
        self.image_processor = ImageProcessor(
            chromedriver_path=chromedriver_path,
            progress_callback=self.update_progress
        )
        
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
    
    def update_progress(self, message, percentage=None):
        """
        Update progress bar dengan pesan dan persentase.
        
        Args:
            message: Pesan untuk ditampilkan
            percentage: Persentase penyelesaian (0-100)
        """
        if percentage is not None:
            self.progress_bar.setValue(percentage)
            self.progress_bar.setFormat(f"{message} - %p%")
        else:
            self.progress_bar.setFormat(message)
        
        # Make sure UI updates in real-time
        QApplication.processEvents()
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle when dragged items enter the window"""
        # Check if the dragged data has URLs (file paths)
        if event.mimeData().hasUrls():
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
            
            file_paths = []
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                # Tambahkan semua file dan folder
                file_paths.append(file_path)
            
            if file_paths:
                self.process_files(file_paths)
    
    def is_image_file(self, file_path):
        """Check if the file is a valid image that can be loaded"""
        if not os.path.isfile(file_path):
            return False
            
        # Check if it's a supported image format
        reader = QImageReader(file_path)
        return reader.canRead()
    
    def process_files(self, file_paths):
        """
        Proses file atau folder yang diberikan
        
        Args:
            file_paths: Daftar path file atau folder
        """
        # Mulai pemrosesan gambar dalam thread terpisah
        self.image_processor.start_processing(file_paths)
        
        # Cek secara periodik apakah thread masih berjalan
        self.check_processor_thread()
    
    def check_processor_thread(self):
        """Cek status thread pemrosesan dan tampilkan statistik jika selesai"""
        if not self.image_processor.processing_thread or not self.image_processor.processing_thread.is_alive():
            # Thread sudah selesai, tampilkan statistik
            if self.image_processor.end_time:  # Pastikan telah diproses
                stats = self.image_processor.get_statistics()
                self.show_statistics(stats)
        else:
            # Thread masih berjalan, cek lagi nanti
            QApplication.processEvents()
            QApplication.instance().processEvents()
            time.sleep(0.1)  # Jeda kecil untuk tidak membebani CPU
            self.check_processor_thread()
    
    def show_statistics(self, stats):
        """Tampilkan dialog statistik"""
        dialog = StatsDialog(self, stats)
        dialog.exec()
    
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
        
    def closeEvent(self, event):
        """Handle when the window is closed"""
        # Stop any ongoing processing
        if hasattr(self, 'image_processor'):
            self.image_processor.stop_processing()
        
        event.accept()

def run_app(base_dir, icon_path=None):
    # Create Qt application
    app = QApplication(sys.argv)
    
    # Create main window
    window = SotongHDApp(base_dir, icon_path)
    
    # Start the event loop
    sys.exit(app.exec())
