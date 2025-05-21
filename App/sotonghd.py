import os
import sys
import time
from datetime import datetime, timedelta
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QMessageBox, QProgressBar, 
                              QVBoxLayout, QDialog, QLabel, QTextBrowser, QPushButton, QFileDialog,
                              QHBoxLayout, QGridLayout, QScrollArea)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtGui import QIcon, QPixmap, QPainter, QImageReader, QDragEnterEvent, QDropEvent
from PySide6.QtCore import Qt, QRect, QPoint, QMimeData, QUrl, Signal, QObject, QTimer
from pathlib import Path
from .background_process import ImageProcessor


class StatsDialog(QDialog):
    """Dialog untuk menampilkan statistik pemrosesan."""
    
    def __init__(self, parent=None, stats=None):
        super().__init__(parent)
        self.stats = stats
        
        # Load UI
        ui_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stats_dialog.ui")
        loader = QUiLoader()
        self.ui = loader.load(ui_file, self)
        
        # Set window icon
        if self.parent() and self.parent().windowIcon():
            self.setWindowIcon(self.parent().windowIcon())
            
            # Set icon in the dialog
            icon = self.parent().windowIcon()
            pixmap = icon.pixmap(64, 64)
            self.ui.iconLabel.setPixmap(pixmap)
            
        # Connect close button
        self.ui.closeButton.clicked.connect(self.accept)
            
        # Fill stats
        self.populate_stats()
        
    def populate_stats(self):
        """Populate stats data to UI elements"""
        if not self.stats:
            return
            
        # Set values
        self.ui.totalSuccessValue.setText(str(self.stats['total_processed']))
        self.ui.totalFailedValue.setText(str(self.stats['total_failed']))
        
        # Total files
        total_files = self.stats['total_processed'] + self.stats['total_failed']
        self.ui.totalFilesValue.setText(str(total_files))
        
        # Time info
        if self.stats['start_time'] and self.stats['end_time']:
            start_time = self.stats['start_time'].strftime("%H:%M:%S")
            end_time = self.stats['end_time'].strftime("%H:%M:%S")
            
            self.ui.startTimeValue.setText(start_time)
            self.ui.endTimeValue.setText(end_time)
            
            # Duration
            duration = timedelta(seconds=int(self.stats['total_duration']))
            self.ui.durationValue.setText(str(duration))
            
        # Folder list
        if 'processed_folders' in self.stats and self.stats['processed_folders']:
            # Clear existing items in the layout
            while self.ui.foldersLayout.count():
                item = self.ui.foldersLayout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
                    
            # Add each folder
            for folder in self.stats['processed_folders']:
                folder_label = QLabel(folder)
                self.ui.foldersLayout.addWidget(folder_label)
        else:
            # Hide folder section if no folders processed
            self.ui.foldersHeaderLabel.setVisible(False)
            self.ui.foldersScrollArea.setVisible(False)

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
        
        # Set the loaded UI as the central widget
        self.setCentralWidget(self.ui.centralWidget())
        
        # Set up drag and drop support
        self.setAcceptDrops(True)
        
        # Get UI elements
        self.dropFrame = self.findChild(QWidget, "dropFrame")
        self.titleLabel = self.findChild(QWidget, "titleLabel")
        self.subtitleLabel = self.findChild(QWidget, "subtitleLabel")
        self.progress_bar = self.findChild(QProgressBar, "progressBar")
          
        # Current displayed image (for processing)
        self.current_image = None
        
        # Initialize image processor
        chromedriver_path = os.path.join(base_dir, "driver", "chromedriver.exe")
        self.image_processor = ImageProcessor(
            chromedriver_path=chromedriver_path,
            progress_callback=self.update_progress
        )
        
        # Apply the theme style to drop frame
        if self.dropFrame:
            self.dropFrame.setStyleSheet("""
                QFrame#dropFrame {
                    border: 2px dashed rgba(88, 29, 239, 0.2);
                    border-radius: 15px;
                    background-color: rgba(88, 29, 239, 0.08);
                }
            """)
          
        # Show the main window
        self.show()
    def update_progress(self, message, percentage=None):
        """
        Update progress bar dengan pesan dan persentase.
        
        Args:
            message: Pesan untuk ditampilkan
            percentage: Persentase penyelesaian (0-100)
        """
        if not self.progress_bar:
            return
            
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
            # Thread masih berjalan, gunakan timer untuk cek lagi nanti
            QApplication.processEvents()
            from PySide6.QtCore import QTimer
            QTimer.singleShot(100, self.check_processor_thread)
    
    def show_statistics(self, stats):
        """Tampilkan dialog statistik"""
        dialog = StatsDialog(self, stats)
        dialog.exec()
    
    def center_on_screen(self):
        """Center the window on the screen."""
        screen_geometry = QApplication.primaryScreen().geometry()
        window_geometry = self.geometry()
        
        x = (screen_geometry.width() - window_geometry.width()) // 2
        y = (screen_geometry.height() - window_geometry.height()) // 2
        
        self.move(x, y)
        
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
