import os
from datetime import timedelta
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QTextBrowser, 
                              QPushButton, QMessageBox)
# Move QUiLoader to proper import
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import Qt
from .logger import logger

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
