import os
from datetime import timedelta
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QTextBrowser, 
                              QPushButton, QMessageBox, QHBoxLayout)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import Qt, QSize, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from .logger import logger

# Import QtAwesome for icons
try:
    import qtawesome as qta
    HAS_AWESOME = True
except ImportError:
    HAS_AWESOME = False
    logger.peringatan("QtAwesome tidak tersedia, ikon tidak akan ditampilkan")

class StatsDialog(QDialog):
    """Dialog untuk menampilkan statistik pemrosesan."""
    
    def __init__(self, parent=None, stats=None):
        super().__init__(parent)
        self.stats = stats
        self.last_folder = None
        
        # If stats contain processed folders, remember the last one for the open folder button
        if stats and 'processed_folders' in stats and stats['processed_folders']:
            # Get the last processed folder
            base_folder = stats['processed_folders'][-1]
            # Create path to UPSCALE folder
            self.last_folder = os.path.join(base_folder, "UPSCALE")
            
        # Set dialog properties
        self.setWindowTitle("Statistik SotongHD")
        self.setMinimumSize(600, 400)
        
        # Create a layout for the dialog
        self.main_layout = QVBoxLayout(self)
        
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
        
        # Add QtAwesome icons if available
        self.setup_awesome_icons()
            
        # Connect buttons
        self.ui.closeButton.clicked.connect(self.accept)
        
        # Connect open folder button if we have a last folder
        self.ui.openFolderButton = self.findChild(QPushButton, "openFolderButton")
        if self.ui.openFolderButton:
            if self.last_folder and os.path.exists(self.last_folder):
                self.ui.openFolderButton.setEnabled(True)
                self.ui.openFolderButton.clicked.connect(self.open_last_folder)
            else:
                self.ui.openFolderButton.setEnabled(False)
                self.ui.openFolderButton.setToolTip("Folder UPSCALE tidak ditemukan")
            
        # Fill stats
        self.populate_stats()
    
    def setup_awesome_icons(self):
        """Add QtAwesome icons to buttons if available"""
        if not HAS_AWESOME:
            return
            
        # Add folder icon to open folder button
        folder_icon = qta.icon('fa5s.folder-open')
        if hasattr(self.ui, 'openFolderButton') and self.ui.openFolderButton:
            self.ui.openFolderButton.setIcon(folder_icon)
            self.ui.openFolderButton.setIconSize(QSize(16, 16))
        
        # Add close icon to close button
        close_icon = qta.icon('fa5s.times-circle')
        if hasattr(self.ui, 'closeButton') and self.ui.closeButton:
            self.ui.closeButton.setIcon(close_icon)
            self.ui.closeButton.setIconSize(QSize(16, 16))
        
        # Don't add icons to the stat labels
        # The issue is likely related to how we're modifying the labels
        # Just leave the text as is to ensure it displays correctly
        
        # Simply skip icon addition to text labels
        logger.info("Skipping icon addition to text labels to ensure proper display")
    
    def open_last_folder(self):
        """Open the last processed UPSCALE folder"""
        if self.last_folder and os.path.exists(self.last_folder):
            logger.info("Membuka folder UPSCALE:", self.last_folder)
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.last_folder))
        else:
            QMessageBox.warning(
                self,
                "Folder Tidak Ditemukan",
                "Folder UPSCALE tidak ditemukan. Pastikan folder masih ada."
            )
        
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
                
            # Update the open folder button state
            if hasattr(self.ui, 'openFolderButton') and self.ui.openFolderButton:
                if self.last_folder and os.path.exists(self.last_folder):
                    self.ui.openFolderButton.setEnabled(True)
                    self.ui.openFolderButton.setToolTip(f"Buka folder: {self.last_folder}")
                else:
                    self.ui.openFolderButton.setEnabled(False)
                    self.ui.openFolderButton.setToolTip("Folder UPSCALE tidak ditemukan")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to populate statistics: {str(e)}")
