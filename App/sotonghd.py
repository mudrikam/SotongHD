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
from .background_process import ImageProcessor, ProgressSignal


class StatsDialog(QDialog):
    """Dialog untuk menampilkan statistik pemrosesan."""
    
    def __init__(self, parent=None, stats=None):
        super().__init__(parent)
        self.stats = stats
        
        # Set dialog properties
        self.setWindowTitle("Statistik SotongHD")
        self.setMinimumSize(600, 400)
        
        # Create a layout for the dialog
        self.main_layout = QVBoxLayout(self)
        
        try:
            # Load UI
            ui_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stats_dialog.ui")
            loader = QUiLoader()
            self.ui = loader.load(ui_file)
            
            # Add the loaded UI to our dialog's layout
            self.main_layout.addWidget(self.ui)
            
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
        
        except Exception as e:
            # Create a fallback UI if loading fails
            error_label = QLabel(f"Error loading stats UI: {str(e)}")
            self.main_layout.addWidget(error_label)
            
            if stats:
                # Display stats as text
                stats_text = QTextBrowser()
                stats_text.setText(
                    f"Total Processed: {stats['total_processed']}\n"
                    f"Total Failed: {stats['total_failed']}\n"
                    f"Total Duration: {timedelta(seconds=int(stats['total_duration']))}\n"
                    f"Start Time: {stats['start_time']}\n"
                    f"End Time: {stats['end_time']}\n"
                )
                self.main_layout.addWidget(stats_text)
                
                # Add folders as text
                if 'processed_folders' in stats and stats['processed_folders']:
                    folders_text = QTextBrowser()
                    folders_text.setText("Processed Folders:\n" + "\n".join(stats['processed_folders']))
                    self.main_layout.addWidget(folders_text)
            
            # Add close button
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.accept)
            self.main_layout.addWidget(close_btn)
        
    def populate_stats(self):
        """Populate stats data to UI elements"""
        if not self.stats:
            return
            
        try:
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
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to populate statistics: {str(e)}")

# Create a progress handler class to receive signals from the background thread
class ProgressHandler(QObject):
    def __init__(self, app):
        super().__init__()
        self.app = app
        
    def handle_progress(self, message, percentage):
        """Handle progress updates from the background thread"""
        # This method is called in the main thread via signal/slot
        self.app.update_progress(message, percentage)

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
        self.iconLabel = self.findChild(QLabel, "iconLabel")
        self.titleLabel = self.findChild(QWidget, "titleLabel")
        self.subtitleLabel = self.findChild(QWidget, "subtitleLabel")
        self.progress_bar = self.findChild(QProgressBar, "progressBar")
        
        # Set icon in the UI using high resolution
        if icon_path and os.path.exists(icon_path) and self.iconLabel:
            # Load the icon with explicitly requesting a larger size
            icon = QIcon(icon_path)
            # Get the largest available size (usually 256x256 for most .ico files)
            available_sizes = icon.availableSizes()
            if available_sizes:
                # Sort sizes and get the largest one
                largest_size = max(available_sizes, key=lambda size: size.width() * size.height())
                pixmap = icon.pixmap(largest_size)
            else:
                # If no sizes available, request a large size explicitly
                pixmap = icon.pixmap(256, 256)
                
            # Scale it down to fit our UI label while maintaining aspect ratio
            self.iconLabel.setPixmap(pixmap.scaled(
                96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))
        
        # Create progress handler to receive signals
        self.progress_handler = ProgressHandler(self)
        
        # Timer for deferred UI updates to prevent recursive repaints
        self.update_timer = QTimer()
        self.update_timer.setSingleShot(True)
        self.update_timer.timeout.connect(self._update_progress_ui)
        self.pending_progress_message = None
        self.pending_progress_percentage = None
        
        # Current displayed image (for processing)
        self.current_image = None
        
        # Initialize image processor
        chromedriver_path = os.path.join(base_dir, "driver", "chromedriver.exe")
        
        # Create a progress signal instance and connect it to our handler
        self.progress_signal = ProgressSignal()
        self.progress_signal.progress.connect(self.progress_handler.handle_progress)
        
        self.image_processor = ImageProcessor(
            chromedriver_path=chromedriver_path,
            progress_signal=self.progress_signal  # Pass signal instead of callback
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
        Schedule progress bar update with a message and percentage.
        Uses a timer to prevent recursive repaints.
        
        Args:
            message: Message to display
            percentage: Completion percentage (0-100)
        """
        if not self.progress_bar:
            return
            
        # Store the updated values for use when the timer fires
        self.pending_progress_message = message
        self.pending_progress_percentage = percentage
        
        # Restart the timer to update UI shortly
        # If timer is already active, this will defer the update 
        # until all pending events are processed
        if not self.update_timer.isActive():
            self.update_timer.start(50)  # 50ms delay

    def _update_progress_ui(self):
        """
        Actually update the UI with the pending progress information.
        This is called by the timer to prevent recursive repaints.
        """
        if not self.progress_bar:
            return
            
        if self.pending_progress_percentage is not None:
            self.progress_bar.setValue(self.pending_progress_percentage)
            self.progress_bar.setFormat(f"{self.pending_progress_message} - %p%")
        else:
            self.progress_bar.setFormat(self.pending_progress_message)

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
