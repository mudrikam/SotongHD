import os
from datetime import timedelta
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QTextBrowser, 
                              QPushButton, QMessageBox, QHBoxLayout)
from PySide6.QtCore import Qt, QSize, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import QFrame, QScrollArea, QWidget, QGridLayout, QVBoxLayout, QHBoxLayout, QSpacerItem, QSizePolicy
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

        # Build the dialog UI in Python (migrated from stats_dialog.ui)
        self.main_layout = QVBoxLayout(self)

        # Header layout with icon and title
        header_layout = QHBoxLayout()
        self.iconLabel = QLabel(self)
        self.iconLabel.setObjectName('iconLabel')
        self.iconLabel.setMinimumSize(64, 64)
        header_layout.addWidget(self.iconLabel)

        self.headerText = QLabel('<h1>SotongHD Report</h1>', self)
        self.headerText.setObjectName('headerText')
        self.headerText.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(self.headerText)

        header_layout.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))
        self.main_layout.addLayout(header_layout)

        # Stats frame
        self.ui = QWidget(self)
        self.ui.setObjectName('statsContainer')
        stats_layout = QVBoxLayout(self.ui)

        stats_frame = QFrame(self.ui)
        stats_frame.setObjectName('statsFrame')
        stats_frame.setStyleSheet('QFrame#statsFrame { border: none; border-radius: 10px; background-color: rgba(161, 161, 161, 0.08); padding: 10px; }')
        stats_frame.setFrameShape(QFrame.StyledPanel)
        stats_frame.setFrameShadow(QFrame.Raised)

        statsGridLayout = QGridLayout(stats_frame)
        statsGridLayout.setObjectName('statsGridLayout')

        # Labels and value placeholders
        totalSuccessLabel = QLabel('Total Gambar Berhasil:', stats_frame)
        totalSuccessLabel.setObjectName('totalSuccessLabel')
        statsGridLayout.addWidget(totalSuccessLabel, 0, 0)
        self.totalSuccessValue = QLabel('0', stats_frame)
        self.totalSuccessValue.setObjectName('totalSuccessValue')
        self.totalSuccessValue.setStyleSheet('color: #2ecc71;')
        statsGridLayout.addWidget(self.totalSuccessValue, 0, 1)

        totalFailedLabel = QLabel('Total Gambar Gagal:', stats_frame)
        statsGridLayout.addWidget(totalFailedLabel, 1, 0)
        self.totalFailedValue = QLabel('0', stats_frame)
        self.totalFailedValue.setObjectName('totalFailedValue')
        self.totalFailedValue.setStyleSheet('color: #e74c3c;')
        statsGridLayout.addWidget(self.totalFailedValue, 1, 1)

        totalFilesLabel = QLabel('Total File:', stats_frame)
        statsGridLayout.addWidget(totalFilesLabel, 2, 0)
        self.totalFilesValue = QLabel('0', stats_frame)
        self.totalFilesValue.setObjectName('totalFilesValue')
        statsGridLayout.addWidget(self.totalFilesValue, 2, 1)

        startTimeLabel = QLabel('Waktu Mulai:', stats_frame)
        statsGridLayout.addWidget(startTimeLabel, 3, 0)
        self.startTimeValue = QLabel('00:00:00', stats_frame)
        self.startTimeValue.setObjectName('startTimeValue')
        statsGridLayout.addWidget(self.startTimeValue, 3, 1)

        endTimeLabel = QLabel('Waktu Selesai:', stats_frame)
        statsGridLayout.addWidget(endTimeLabel, 4, 0)
        self.endTimeValue = QLabel('00:00:00', stats_frame)
        self.endTimeValue.setObjectName('endTimeValue')
        statsGridLayout.addWidget(self.endTimeValue, 4, 1)

        durationLabel = QLabel('Durasi:', stats_frame)
        statsGridLayout.addWidget(durationLabel, 5, 0)
        self.durationValue = QLabel('0:00:00', stats_frame)
        self.durationValue.setObjectName('durationValue')
        statsGridLayout.addWidget(self.durationValue, 5, 1)

        stats_layout.addWidget(stats_frame)

        # Folders header and scroll area (to match original UI)
        self.foldersHeaderLabel = QLabel('Folder yang Diproses:', self.ui)
        self.foldersHeaderLabel.setObjectName('foldersHeaderLabel')
        stats_layout.addWidget(self.foldersHeaderLabel)

        self.foldersScrollArea = QScrollArea(self.ui)
        self.foldersScrollArea.setObjectName('foldersScrollArea')
        self.foldersScrollArea.setWidgetResizable(True)
        scroll_contents = QWidget()
        scroll_contents.setObjectName('scrollAreaWidgetContents')
        self.foldersLayout = QVBoxLayout(scroll_contents)
        self.foldersLayout.setObjectName('foldersLayout')
        self.foldersScrollArea.setWidget(scroll_contents)
        stats_layout.addWidget(self.foldersScrollArea)

        # Attach created widgets to self.ui so existing code using self.ui.<name> works
        self.ui.totalSuccessValue = self.totalSuccessValue
        self.ui.totalFailedValue = self.totalFailedValue
        self.ui.totalFilesValue = self.totalFilesValue
        self.ui.startTimeValue = self.startTimeValue
        self.ui.endTimeValue = self.endTimeValue
        self.ui.durationValue = self.durationValue
        self.ui.foldersLayout = self.foldersLayout
        self.ui.foldersHeaderLabel = self.foldersHeaderLabel
        self.ui.foldersScrollArea = self.foldersScrollArea

        self.main_layout.addWidget(self.ui)

        # Set window icon and dialog icon label
        if self.parent() and self.parent().windowIcon():
            self.setWindowIcon(self.parent().windowIcon())
            icon = self.parent().windowIcon()
            pixmap = icon.pixmap(64, 64)
            if hasattr(self, 'iconLabel'):
                self.iconLabel.setPixmap(pixmap)
        
        # Add QtAwesome icons if available
        self.setup_awesome_icons()

        # Buttons: create openFolderButton and closeButton consistent with the .ui
        # Button layout
        button_layout = QHBoxLayout()
        self.openFolderButton = QPushButton('Buka Folder', self)
        self.openFolderButton.setObjectName('openFolderButton')
        button_layout.addWidget(self.openFolderButton)

        self.closeButton = QPushButton('Tutup', self)
        self.closeButton.setObjectName('closeButton')
        button_layout.addWidget(self.closeButton)

        self.main_layout.addLayout(button_layout)

        # Connect buttons
        self.closeButton.clicked.connect(self.accept)
        if self.openFolderButton:
            if self.last_folder and os.path.exists(self.last_folder):
                self.openFolderButton.setEnabled(True)
                self.openFolderButton.clicked.connect(self.open_last_folder)
            else:
                self.openFolderButton.setEnabled(False)
                self.openFolderButton.setToolTip("Folder UPSCALE tidak ditemukan")
        # Fill stats
        # Also attach buttons to self.ui for compatibility
        self.ui.openFolderButton = self.openFolderButton
        self.ui.closeButton = self.closeButton

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
