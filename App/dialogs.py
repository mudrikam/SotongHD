import os
from datetime import timedelta
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QTextBrowser, 
                              QPushButton, QMessageBox, QHBoxLayout)
from PySide6.QtCore import Qt, QSize, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import QFrame, QScrollArea, QWidget, QGridLayout, QVBoxLayout, QHBoxLayout, QSpacerItem, QSizePolicy
from .logger import logger

import qtawesome as qta

class StatsDialog(QDialog):
    
    def __init__(self, parent=None, stats=None):
        super().__init__(parent)
        self.stats = stats
        self.last_folder = None
        
        if stats and 'processed_folders' in stats and stats['processed_folders']:
            last_folder = None
            for source_folder in reversed(stats['processed_folders']):
                upscale_folder = os.path.join(source_folder, 'UPSCALE')
                if os.path.exists(upscale_folder) and os.path.isdir(upscale_folder):
                    last_folder = upscale_folder
                    break
            self.last_folder = last_folder
            
        self.setWindowTitle("Statistik SotongHD")
        self.setMinimumSize(600, 400)

        self.main_layout = QVBoxLayout(self)

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

        upscaleLevelLabel = QLabel('Level Upscale:', stats_frame)
        statsGridLayout.addWidget(upscaleLevelLabel, 6, 0)
        self.upscaleLevelValue = QLabel('2x', stats_frame)
        self.upscaleLevelValue.setObjectName('upscaleLevelValue')
        self.upscaleLevelValue.setStyleSheet('color: #9b59b6; font-weight: bold;')
        statsGridLayout.addWidget(self.upscaleLevelValue, 6, 1)

        stats_layout.addWidget(stats_frame)

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

        self.ui.totalSuccessValue = self.totalSuccessValue
        self.ui.totalFailedValue = self.totalFailedValue
        self.ui.totalFilesValue = self.totalFilesValue
        self.ui.startTimeValue = self.startTimeValue
        self.ui.endTimeValue = self.endTimeValue
        self.ui.durationValue = self.durationValue
        self.ui.upscaleLevelValue = self.upscaleLevelValue
        self.ui.foldersLayout = self.foldersLayout
        self.ui.foldersHeaderLabel = self.foldersHeaderLabel
        self.ui.foldersScrollArea = self.foldersScrollArea

        self.main_layout.addWidget(self.ui)

        if self.parent() and self.parent().windowIcon():
            self.setWindowIcon(self.parent().windowIcon())
            icon = self.parent().windowIcon()
            pixmap = icon.pixmap(64, 64)
            if hasattr(self, 'iconLabel'):
                self.iconLabel.setPixmap(pixmap)

        button_layout = QHBoxLayout()
        self.openFolderButton = QPushButton('Buka Folder', self)
        self.openFolderButton.setObjectName('openFolderButton')
        # match main window button appearance
        self.openFolderButton.setMinimumHeight(36)
        self.openFolderButton.setStyleSheet("QPushButton {\n  background-color: rgba(161, 161, 161, 0.08);\n  border-radius: 10px;\n  padding: 8px 16px;\n}\nQPushButton:hover {\n  background-color: rgba(88, 29, 239, 0.7);\n  border: none;\n}\nQPushButton:pressed {\n  background-color: rgba(88, 29, 239, 1.0);\n}")
        button_layout.addWidget(self.openFolderButton)

        self.closeButton = QPushButton('Tutup', self)
        self.closeButton.setObjectName('closeButton')
        self.closeButton.setMinimumHeight(36)
        self.closeButton.setStyleSheet("QPushButton {\n  background-color: rgba(161, 161, 161, 0.08);\n  border-radius: 10px;\n  padding: 8px 16px;\n}\nQPushButton:hover {\n  background-color: rgba(231, 76, 60, 0.7);\n  border: none;\n}\nQPushButton:pressed {\n  background-color: rgba(231, 76, 60, 1.0);\n}\nQPushButton:disabled {\n  background-color: rgba(161, 161, 161, 0.04);\n}")
        button_layout.addWidget(self.closeButton)

        self.main_layout.addLayout(button_layout)

        self.closeButton.clicked.connect(self.accept)
        if self.openFolderButton:
            if self.last_folder and os.path.exists(self.last_folder):
                self.openFolderButton.setEnabled(True)
                self.openFolderButton.clicked.connect(self.open_last_folder)
            else:
                self.openFolderButton.setEnabled(False)
                self.openFolderButton.setToolTip("Folder UPSCALE tidak ditemukan")

        self.ui.openFolderButton = self.openFolderButton
        self.ui.closeButton = self.closeButton
        self.setup_awesome_icons()

        self.populate_stats()
    
    def setup_awesome_icons(self):
        folder_icon = qta.icon('fa5s.folder-open')
        self.openFolderButton.setIcon(folder_icon)
        self.openFolderButton.setIconSize(QSize(20, 20))
        self.openFolderButton.setMinimumHeight(36)

        close_icon = qta.icon('fa5s.times-circle')
        self.closeButton.setIcon(close_icon)
        self.closeButton.setIconSize(QSize(20, 20))
        self.closeButton.setMinimumHeight(36)
    
    def open_last_folder(self):
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
        if not self.stats:
            return
        try:
            self.ui.totalSuccessValue.setText(str(self.stats['total_processed']))
            self.ui.totalFailedValue.setText(str(self.stats['total_failed']))
            total_files = self.stats['total_processed'] + self.stats['total_failed']
            self.ui.totalFilesValue.setText(str(total_files))
            if self.stats['start_time'] and self.stats['end_time']:
                start_time = self.stats['start_time'].strftime("%H:%M:%S")
                end_time = self.stats['end_time'].strftime("%H:%M:%S")
                self.ui.startTimeValue.setText(start_time)
                self.ui.endTimeValue.setText(end_time)
                duration = timedelta(seconds=int(self.stats['total_duration']))
                self.ui.durationValue.setText(str(duration))
            
            # Set upscale level
            upscale_level = self.stats.get('upscale_level', '2x')
            upscale_passes = self.stats.get('upscale_passes', 1)
            self.ui.upscaleLevelValue.setText(f"{upscale_level} ({upscale_passes} pass{'es' if upscale_passes > 1 else ''})")
            
            if 'processed_folders' in self.stats and self.stats['processed_folders']:
                while self.ui.foldersLayout.count():
                    item = self.ui.foldersLayout.takeAt(0)
                    if item.widget():
                        item.widget().deleteLater()
                for folder in self.stats['processed_folders']:
                    folder_label = QLabel(folder)
                    self.ui.foldersLayout.addWidget(folder_label)
            else:
                self.ui.foldersHeaderLabel.setVisible(False)
                self.ui.foldersScrollArea.setVisible(False)
                
            if hasattr(self.ui, 'openFolderButton') and self.ui.openFolderButton:
                if self.last_folder and os.path.exists(self.last_folder):
                    self.ui.openFolderButton.setEnabled(True)
                    self.ui.openFolderButton.setToolTip(f"Buka folder: {self.last_folder}")
                else:
                    self.ui.openFolderButton.setEnabled(False)
                    self.ui.openFolderButton.setToolTip("Folder UPSCALE tidak ditemukan")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to populate statistics: {str(e)}")
