import os
import sys
from datetime import datetime
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QMessageBox, QProgressBar, 
                              QVBoxLayout, QLabel, QPushButton, QFileDialog,
                              QHBoxLayout, QGridLayout, QScrollArea, QSizePolicy, QTextEdit, QCheckBox)
# Fix the import for QUiLoader - it should be from QtUiTools, not QtWidgets
from PySide6.QtGui import QIcon, QPixmap, QDragEnterEvent, QDropEvent
from PySide6.QtCore import Qt, QTimer, QSize, QUrl, Signal, QObject
from PySide6.QtWidgets import QFrame, QSpacerItem
from pathlib import Path

from .background_process import ImageProcessor, ProgressSignal, FileUpdateSignal
from .logger import logger
from .ui_helpers import (ScalableImageLabel, center_window_on_screen, setup_drag_drop_style, 
                       setup_format_toggle, set_application_icon)
from .progress_handler import ProgressHandler, ProgressUIManager
from .file_processor import (is_image_file, open_folder_dialog, open_files_dialog, 
                           open_whatsapp_group, show_statistics, confirm_stop_processing)
from .config_manager import ConfigManager

# Import QtAwesome for icons - make sure it's installed
try:
    import qtawesome as qta
    logger.info("QtAwesome tersedia, ikon akan ditampilkan")
except ImportError:
    logger.peringatan("QtAwesome tidak tersedia, ikon tidak akan ditampilkan")
    qta = None

class SotongHDApp(QMainWindow):
    def __init__(self, base_dir, icon_path=None):
        super().__init__()
        
        logger.info("Memulai aplikasi SotongHD")
        
        # Store the base directory
        self.base_dir = base_dir
        
        # Store original title text
        self.original_title_text = "LEMPARKAN GAMBAR KE SINI!"
        
        # Set icon if provided
        if icon_path and os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            # Set application-wide icon
            QApplication.setWindowIcon(QIcon(icon_path))
        else:
            logger.peringatan("Ikon aplikasi tidak ditemukan", icon_path)
        
        # Main window properties
        self.setGeometry(100, 100, 700, 700)
        self.setWindowTitle("SotongHD")

        # Center the window on the screen
        center_window_on_screen(self)

        # Central widget
        central_widget = QWidget(self)
        central_widget.setObjectName("centralwidget")
        main_vlayout = QVBoxLayout(central_widget)
        main_vlayout.setObjectName("verticalLayout_2")

        # Top area with drop frame
        top_vlayout = QVBoxLayout()
        top_vlayout.setObjectName("verticalLayout")

        # Drop frame
        drop_frame = QFrame(central_widget)
        drop_frame.setObjectName("dropFrame")
        drop_frame.setFrameShape(QFrame.StyledPanel)
        drop_frame.setFrameShadow(QFrame.Raised)
        drop_frame.setStyleSheet("QFrame#dropFrame {\n  border: 2px dashed rgba(88, 29, 239, 0.08);\n  border-radius: 15px;\n  background-color: rgba(88, 29, 239, 0.08);\n}\n")

        drop_layout = QVBoxLayout(drop_frame)
        drop_layout.setObjectName("dropAreaLayout")

        # Top spacer
        self.topSpacer = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        drop_layout.addItem(self.topSpacer)

        # Icon label
        self.iconLabel = QLabel(drop_frame)
        self.iconLabel.setObjectName("iconLabel")
        self.iconLabel.setMinimumSize(96, 96)
        # Try to set pixmap from expected locations
        possible_icon = os.path.join(base_dir, "sotonghd.ico")
        if os.path.exists(possible_icon):
            self.iconLabel.setPixmap(QPixmap(possible_icon))
        self.iconLabel.setAlignment(Qt.AlignCenter)
        drop_layout.addWidget(self.iconLabel, alignment=Qt.AlignCenter)

        # Title label
        self.titleLabel = QLabel("LEMPARKAN GAMBAR KE SINI!", drop_frame)
        self.titleLabel.setObjectName("titleLabel")
        title_font = self.titleLabel.font()
        title_font.setPointSize(20)
        title_font.setBold(True)
        self.titleLabel.setFont(title_font)
        self.titleLabel.setStyleSheet("color : rgba(138, 60, 226, 0.62);")
        self.titleLabel.setAlignment(Qt.AlignCenter)
        drop_layout.addWidget(self.titleLabel)

        # Subtitle label
        self.subtitleLabel = QLabel(drop_frame)
        self.subtitleLabel.setObjectName("subtitleLabel")
        subtitle_font = self.subtitleLabel.font()
        subtitle_font.setPointSize(10)
        self.subtitleLabel.setFont(subtitle_font)
        self.subtitleLabel.setStyleSheet("color : rgba(148, 139, 160, 0.7);")
        self.subtitleLabel.setAlignment(Qt.AlignCenter)
        self.subtitleLabel.setWordWrap(True)
        self.subtitleLabel.setText("""
            Script ini hanya mengunggah gambar ke situs Picsart dan menggunakan fitur upscale otomatis di sana.

            Upscale tidak dilakukan oleh aplikasi ini, tapi oleh server Picsart.
            Hasil akan disimpan otomatis ke folder 'UPSCALE' sumber file asli. Fitur gratis Picsart hanya mendukung hingga 2x upscale. Gunakan seperlunya.
            """)
        drop_layout.addWidget(self.subtitleLabel)

        # Bottom spacer
        self.bottomSpacer = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        drop_layout.addItem(self.bottomSpacer)

        top_vlayout.addWidget(drop_frame)
        main_vlayout.addLayout(top_vlayout)

        # Progress bar
        self.progress_bar = QProgressBar(central_widget)
        self.progress_bar.setObjectName("progressBar")
        self.progress_bar.setMinimumSize(0, 30)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Ready")
        self.progress_bar.setStyleSheet("QProgressBar {\n  border: none;\n  border-radius: 10px;\n  background-color: rgba(161, 161, 161, 0.08);\n  text-align: center;\n  font-weight: bold;\n  margin: 0px;\n  padding: 0px;\n  height: 30px;\n}\nQProgressBar::chunk {\n  background-color: #5720e3;\n  border-radius: 10px;\n}")
        main_vlayout.addWidget(self.progress_bar)

        # Log display
        self.log_display = QTextEdit(central_widget)
        self.log_display.setObjectName("logDisplay")
        self.log_display.setMinimumSize(0, 100)
        self.log_display.setMaximumHeight(150)
        self.log_display.setReadOnly(True)
        self.log_display.setStyleSheet("QTextEdit {\n  border: none;\n  border-radius: 10px;\n  background-color: rgba(161, 161, 161, 0.08);\n  color: rgba(88, 29, 239, 0.7);\n  padding: 8px;\n  font-family: 'Consolas', monospace;\n  font-size: 9pt;\n}\n")
        main_vlayout.addWidget(self.log_display)

        # Buttons row
        buttons_layout = QHBoxLayout()
        buttons_layout.setObjectName("buttonsLayout")

        # WhatsApp button
        self.whatsappButton = QPushButton(central_widget)
        self.whatsappButton.setObjectName("whatsappButton")
        self.whatsappButton.setMinimumSize(40, 40)
        self.whatsappButton.setToolTip("Join WhatsApp Group")
        self.whatsappButton.setStyleSheet("QPushButton {\n  background-color: rgba(161, 161, 161, 0.08);\n  color: rgba(88, 29, 239, 0.7);\n  border-radius: 20px;\n  padding: 8px;\n}\nQPushButton:hover {\n  background-color: rgba(37, 211, 102, 0.8);\n  color: white;\n  border: none;\n}\nQPushButton:pressed {\n  background-color: rgba(37, 211, 102, 1.0);\n}")
        buttons_layout.addWidget(self.whatsappButton)

        # Format selector layout
        buttons_layout.addStretch()
        format_layout = QHBoxLayout()
        format_layout.setSpacing(4)
        self.formatLabel = QLabel("PNG", central_widget)
        self.formatLabel.setObjectName("formatLabel")
        self.formatLabel.setStyleSheet("color: rgb(85, 0, 255);")
        format_layout.addWidget(self.formatLabel)

        self.formatToggle = QCheckBox(central_widget)
        self.formatToggle.setObjectName("formatToggle")
        self.formatToggle.setMinimumSize(60, 24)
        self.formatToggle.setMaximumSize(60, 24)
        self.formatToggle.setStyleSheet("QCheckBox { spacing: 0px; }\nQCheckBox::indicator { width: 60px; height: 24px; border-radius: 12px; background-color: rgba(88, 29, 239, 0.3);}\nQCheckBox::indicator:checked { background-color: rgba(52, 152, 219, 0.5);} ")
        format_layout.addWidget(self.formatToggle)

        self.formatLabel2 = QLabel("JPG", central_widget)
        self.formatLabel2.setObjectName("formatLabel2")
        self.formatLabel2.setStyleSheet("color: rgb(0, 125, 139);")
        format_layout.addWidget(self.formatLabel2)

        buttons_layout.addLayout(format_layout)
        buttons_layout.addStretch()

        # Stop button
        self.stopButton = QPushButton("Stop", central_widget)
        self.stopButton.setObjectName("stopButton")
        self.stopButton.setEnabled(False)
        self.stopButton.setMinimumSize(90, 40)
        self.stopButton.setStyleSheet("QPushButton {\n  background-color: rgba(161, 161, 161, 0.08);\n  border-radius: 10px;\n  padding: 8px 16px;\n}\nQPushButton:hover {\n  background-color: rgba(231, 76, 60, 0.7);\n  color: white;\n  border: none;\n}\nQPushButton:pressed {\n  background-color: rgba(231, 76, 60, 1.0);\n}\nQPushButton:disabled {\n  background-color: rgba(161, 161, 161, 0.04);\n  color: rgba(161, 161, 161, 0.4);\n}")
        buttons_layout.addWidget(self.stopButton)

        # Open Folder and Open Files buttons
        self.openFolderButton = QPushButton(" Open Folder", central_widget)
        self.openFolderButton.setObjectName("openFolderButton")
        self.openFolderButton.setMinimumSize(180, 40)
        self.openFolderButton.setStyleSheet("QPushButton {\n  background-color: rgba(161, 161, 161, 0.08);\n  border-radius: 10px;\n  padding: 8px 16px;\n}\nQPushButton:hover {\n  background-color: rgba(88, 29, 239, 0.7);\n  color: white;\n  border: none;\n}\nQPushButton:pressed {\n  background-color: rgba(88, 29, 239, 1.0);\n}")
        buttons_layout.addWidget(self.openFolderButton)

        self.openFilesButton = QPushButton("Open Files", central_widget)
        self.openFilesButton.setObjectName("openFilesButton")
        self.openFilesButton.setMinimumSize(180, 40)
        self.openFilesButton.setStyleSheet(self.openFolderButton.styleSheet())
        buttons_layout.addWidget(self.openFilesButton)

        main_vlayout.addLayout(buttons_layout)

        # Menu bar / status bar placeholders (not strictly required)
        self.setCentralWidget(central_widget)
        # Keep reference for code that expected self.ui
        self.ui = central_widget
        
        # Set up drag and drop support
        self.setAcceptDrops(True)
        
        self.setup_ui_elements()
        self.setup_buttons()
        self.setup_thumbnail_label()
        self.setup_progress_handler()
        
        # Initialize image processor
        self.setup_image_processor(base_dir)
        
        # Apply the theme style to drop frame
        if self.dropFrame:
            setup_drag_drop_style(self.dropFrame)
          
        # Show the main window
        self.show()
    
    def setup_ui_elements(self):
        """Find and setup UI elements"""
        # Get UI elements
        # We constructed the widgets in __init__, just reference them
        # Keep the same attribute names used across the codebase
        self.dropFrame = getattr(self, 'dropFrame', None)
        # If not created earlier, try to find by objectName
        if not self.dropFrame:
            self.dropFrame = self.findChild(QFrame, "dropFrame")
        # iconLabel, titleLabel, subtitleLabel, progress_bar, log_display exist as attributes
        self.iconLabel = getattr(self, 'iconLabel', self.findChild(QLabel, "iconLabel"))
        self.titleLabel = getattr(self, 'titleLabel', self.findChild(QLabel, "titleLabel"))
        self.subtitleLabel = getattr(self, 'subtitleLabel', self.findChild(QLabel, "subtitleLabel"))
        self.progress_bar = getattr(self, 'progress_bar', self.findChild(QProgressBar, "progressBar"))
        self.log_display = getattr(self, 'log_display', self.findChild(QTextEdit, "logDisplay"))
        
    # Spacers we created in __init__
    # self.topSpacer and self.bottomSpacer are QSpacerItem instances
        
        # Connect the logger to the UI log display
        if self.log_display:
            logger.set_log_widget(self.log_display)
            
    # Ensure proper expansion behavior
        self.configure_size_policies()
        
        # Set high resolution icon if available
        if self.iconLabel:
            self.setup_high_res_icon()
        
        # Set up format toggle
        self.formatToggle = self.findChild(QCheckBox, "formatToggle")
        self.formatLabel = self.findChild(QLabel, "formatLabel")
        self.formatLabel2 = self.findChild(QLabel, "formatLabel2")
        
        # Initialize config manager
        self.config_manager = ConfigManager(self.base_dir)
        
        # Set up format toggle using helper function
        self.formatToggle, self.formatLabel, self.formatLabel2 = setup_format_toggle(self, self.config_manager)
    
    def setup_buttons(self):
        """Setup buttons and their icons"""
        # Get the buttons
        self.openFolderButton = self.findChild(QPushButton, "openFolderButton")
        self.openFilesButton = self.findChild(QPushButton, "openFilesButton")
        self.whatsappButton = self.findChild(QPushButton, "whatsappButton")
        self.stopButton = self.findChild(QPushButton, "stopButton")
        
        # Set stopButton to disabled initially (since no processing is running)
        if self.stopButton:
            self.stopButton.setEnabled(False)
            self.stopButton.clicked.connect(self.stop_processing)
        
        # Add icons to buttons if qtawesome is available
        if qta:
            # WhatsApp button with whatsapp icon
            whatsapp_icon = qta.icon('fa5b.whatsapp')
            if self.whatsappButton:
                self.whatsappButton.setIcon(whatsapp_icon)
                self.whatsappButton.setIconSize(QSize(24, 24))
                self.whatsappButton.clicked.connect(self.on_whatsapp_button_click)
            
            # Open Folder button with folder icon
            folder_icon = qta.icon('fa5s.folder-open')
            if self.openFolderButton:
                self.openFolderButton.setIcon(folder_icon)
                self.openFolderButton.setIconSize(QSize(16, 16))
                self.openFolderButton.clicked.connect(self.on_open_folder_click)
            
            # Open Files button with file icon
            files_icon = qta.icon('fa5s.file-image')
            if self.openFilesButton:
                self.openFilesButton.setIcon(files_icon)
                self.openFilesButton.setIconSize(QSize(16, 16))
                self.openFilesButton.clicked.connect(self.on_open_files_click)
            
            # Stop button with stop icon
            stop_icon = qta.icon('fa5s.stop')
            if self.stopButton:
                self.stopButton.setIcon(stop_icon)
                self.stopButton.setIconSize(QSize(16, 16))
        else:
            # If qtawesome is not available, connect buttons without icons
            if self.whatsappButton:
                self.whatsappButton.setText("WA")
                self.whatsappButton.clicked.connect(self.on_whatsapp_button_click)
            
            if self.openFolderButton:
                self.openFolderButton.clicked.connect(self.on_open_folder_click)
                
            if self.openFilesButton:
                self.openFilesButton.clicked.connect(self.on_open_files_click)
    
    def setup_thumbnail_label(self):
        """Setup the thumbnail label for displaying images"""
        # Create a scalable image label for thumbnails with proper size policy
        self.thumbnail_label = ScalableImageLabel()
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.hide()  # Initially hidden
        self.thumbnail_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Keep reference to original title label properties
        if self.titleLabel:
            self.original_title_font = self.titleLabel.font()
            self.original_title_text = self.titleLabel.text()
            self.original_title_alignment = self.titleLabel.alignment()
            
            # Get title label's parent layout
            parent_layout = self.titleLabel.parentWidget().layout()
            title_index = parent_layout.indexOf(self.titleLabel)
            
            # Insert thumbnail label at the same position
            if title_index >= 0:
                parent_layout.insertWidget(title_index, self.thumbnail_label)
    
    def setup_progress_handler(self):
        """Setup progress handling"""
        # Create progress handler to receive signals
        self.progress_handler = ProgressHandler(self)
        
        # Create UI manager for progress updates
        self.progress_ui_manager = ProgressUIManager(self.progress_bar)
        
        # Current displayed image (for processing)
        self.current_image = None
    
    def setup_image_processor(self, base_dir):
        """Initialize the image processor"""
        try:
            chromedriver_path = os.path.join(base_dir, "driver", "chromedriver.exe")
            
            # Create a progress signal instance and connect it to our handler
            self.progress_signal = ProgressSignal()
            self.progress_signal.progress.connect(self.progress_handler.handle_progress)
            
            # Create a file update signal and connect it
            self.file_update_signal = FileUpdateSignal()
            self.file_update_signal.file_update.connect(self.progress_handler.handle_file_update)
            
            self.image_processor = ImageProcessor(
                chromedriver_path=chromedriver_path,
                progress_signal=self.progress_signal,
                file_update_signal=self.file_update_signal,
                config_manager=self.config_manager
            )
            logger.sukses("Aplikasi SotongHD siap digunakan")
            logger.info("Untuk memulai, seret dan lepas gambar atau folder ke area drop")
        except Exception as e:
            logger.kesalahan("Gagal menginisialisasi image processor", str(e))
            QMessageBox.critical(self, "Error", f"Gagal menginisialisasi processor: {str(e)}")
    
    def setup_high_res_icon(self):
        """Setup a high resolution icon in the UI"""
        # Try different possible icon paths
        possible_paths = [
            self.windowIcon().name(),
            os.path.join(self.base_dir, "sotonghd.ico"),
            os.path.join(self.base_dir, "App", "sotonghd.ico"),
            os.path.join(self.base_dir, "App", "sotong_bg.png")
        ]
        
        # Try each path until one works
        for path in possible_paths:
            if path and os.path.exists(path):
                if set_application_icon(self, path):
                    break
        else:
            logger.peringatan("Tidak dapat menemukan ikon aplikasi")
    
    def configure_size_policies(self):
        """Configure size policies for UI elements"""
        # Main window should be able to resize
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Central widget should expand
        central_widget = self.centralWidget()
        if central_widget:
            central_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            
        # Configure resize behavior for dropFrame to allow it to expand
        if self.dropFrame:
            # Set size policy to expand in both directions with a high stretch factor
            self.dropFrame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            
            # Find the vertical layout that contains the dropFrame
            parent_layout = None
            if self.dropFrame.parent() and self.dropFrame.parent().layout():
                parent_layout = self.dropFrame.parent().layout()
                # Ensure the layout stretches
                for i in range(parent_layout.count()):
                    parent_layout.setStretch(i, 1)
            
            # Make the layout inside the dropFrame stretch properly
            if self.dropFrame.layout():
                # Set stretch for all items in the dropArea layout
                layout = self.dropFrame.layout()
                layout.setStretch(0, 1)  # Top spacer gets stretch factor
                layout.setStretch(4, 1)  # Bottom spacer gets stretch factor
        
        # Set all labels to have proper sizing policies
        if self.titleLabel:
            self.titleLabel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        
        if self.subtitleLabel:
            self.subtitleLabel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
    
    # Drag and drop handling
    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle when dragged items enter the window"""
        # More robust check for valid drag data
        mime_data = event.mimeData()
        if mime_data and mime_data.hasUrls():
            # Only accept if there's at least one valid local file
            has_local_files = any(url.isLocalFile() for url in mime_data.urls())
            if has_local_files:
                event.acceptProposedAction()
                setup_drag_drop_style(self.dropFrame, highlighted=True)
                return
        event.ignore()
        
    def dragLeaveEvent(self, event):
        """Handle when dragged items leave the window"""
        setup_drag_drop_style(self.dropFrame)
        
    def dragMoveEvent(self, event):
        """Handle when dragged items move within the window"""
        # We already checked the mime data in dragEnterEvent, so just accept
        if event.mimeData().hasUrls():
            event.acceptProposedAction()    
            
    def dropEvent(self, event: QDropEvent):
        """Handle when items are dropped into the window"""
        # Reset the dropFrame style
        setup_drag_drop_style(self.dropFrame)
        
        # Process the dropped files
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            
            file_paths = []
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                # Tambahkan semua file dan folder
                file_paths.append(file_path)
            
            if file_paths:
                paths_str = ", ".join([os.path.basename(p) for p in file_paths])
                logger.info(f"File diterima: {len(file_paths)} item", paths_str)
                self.process_files(file_paths)
    
    # Button handlers
    def on_open_folder_click(self):
        folder_path = open_folder_dialog(self)
        if folder_path:
            self.process_files([folder_path])
    
    def on_open_files_click(self):
        file_paths = open_files_dialog(self)
        if file_paths:
            self.process_files(file_paths)
    
    def on_whatsapp_button_click(self):
        open_whatsapp_group()
    
    # Processing methods
    def process_files(self, file_paths):
        """
        Proses file atau folder yang diberikan
        
        Args:
            file_paths: Daftar path file atau folder
        """
        # Reset UI to initial state
        self.restore_title_label()
        
        # Log file yang akan diproses
        paths_str = ", ".join([os.path.basename(p) for p in file_paths])
        logger.info(f"Memproses {len(file_paths)} item", paths_str)
        
        # Enable stop button
        if self.stopButton:
            self.stopButton.setEnabled(True)
        
        # Disable other buttons during processing
        if self.openFolderButton:
            self.openFolderButton.setEnabled(False)
        if self.openFilesButton:
            self.openFilesButton.setEnabled(False)
        
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
                show_statistics(self, stats)
            
            # Reset UI buttons
            self.reset_ui_buttons()
        else:
            # Thread masih berjalan, gunakan timer untuk cek lagi nanti
            QApplication.processEvents()
            QTimer.singleShot(100, self.check_processor_thread)
    
    def stop_processing(self):
        """Hentikan pemrosesan dan reset UI"""
        logger.info("Menghentikan pemrosesan berdasarkan permintaan pengguna")
        
        # Show a confirmation dialog
        if confirm_stop_processing(self):
            # Stop the image processor
            if hasattr(self, 'image_processor'):
                self.image_processor.stop_processing()
            
            # Reset UI state
            self.restore_title_label()
            self.reset_ui_buttons()
            
            # Update progress bar to show cancellation
            if self.progress_bar:
                self.progress_bar.setValue(0)
                self.progress_bar.setFormat("Proses dibatalkan oleh pengguna")
            
            logger.peringatan("Proses dibatalkan oleh pengguna")
    
    def reset_ui_buttons(self):
        """Reset status tombol UI setelah pemrosesan selesai"""
        # Disable stop button
        if self.stopButton:
            self.stopButton.setEnabled(False)
        
        # Enable folder and files buttons
        if self.openFolderButton:
            self.openFolderButton.setEnabled(True)
        if self.openFilesButton:
            self.openFilesButton.setEnabled(True)
    
    # UI update methods
    def update_progress(self, message, percentage=None):
        """
        Forward progress updates to the UI manager
        
        Args:
            message: Message to display
            percentage: Completion percentage (0-100)
        """
        self.progress_ui_manager.update_progress(message, percentage)

    def update_thumbnail(self, file_path):
        """
        Update the title label to show a thumbnail of the current image
        
        Args:
            file_path: Path to the image file
        """
        if not file_path or not os.path.exists(file_path):
            logger.peringatan("Thumbnail tidak dapat ditampilkan, file tidak ditemukan", file_path)
            return
            
        try:
            # Hide icon label during processing
            if hasattr(self, 'iconLabel') and self.iconLabel:
                self.iconLabel.hide()
                
            # Completely remove spacers from layout instead of just hiding them
            # This ensures they don't constrain the layout expansion
            if hasattr(self, 'topSpacer') and self.topSpacer and self.dropFrame and self.dropFrame.layout():
                layout = self.dropFrame.layout()
                layout.removeItem(self.topSpacer)
                
            if hasattr(self, 'bottomSpacer') and self.bottomSpacer and self.dropFrame and self.dropFrame.layout():
                layout = self.dropFrame.layout()
                layout.removeItem(self.bottomSpacer)
                
            # Set the thumbnail label to take up maximum space
            if hasattr(self, 'thumbnail_label'):
                self.thumbnail_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                self.thumbnail_label.setMinimumHeight(300)  # Set a larger minimum height
                
            # Get the parent layout of the title label
            if hasattr(self, 'titleLabel') and self.titleLabel:
                # Hide the title label and show the thumbnail label
                self.titleLabel.hide()
                self.thumbnail_label.show()
                
                # Get the layout
                parent_layout = self.titleLabel.parentWidget().layout()
                if parent_layout:
                    # Make sure the thumbnail gets most of the layout priority
                    title_index = parent_layout.indexOf(self.thumbnail_label)
                    if title_index >= 0:
                        parent_layout.setStretch(title_index, 10)  # Give it high stretch priority
                
                # Load the image in the scalable label
                success = self.thumbnail_label.setImagePath(file_path)
                
                if not success:
                    logger.peringatan("Gagal memuat thumbnail", file_path)
                    self.restore_title_label()
                    return
                
                # Update subtitle to show file name
                file_name = os.path.basename(file_path)
                if self.subtitleLabel:
                    self.subtitleLabel.setText(f"Memproses: {file_name}")
                    
            # Force a layout update
            if self.dropFrame:
                self.dropFrame.updateGeometry()
                self.dropFrame.layout().activate()
                
        except Exception as e:
            logger.kesalahan("Error menampilkan thumbnail", f"{file_path} - {str(e)}")
            print(f"Error showing thumbnail: {e}")
            self.restore_title_label()  # Restore on error
    
    def restore_title_label(self):
        """Restore the title label to its original state"""
        try:
            # Show icon label when finished
            if hasattr(self, 'iconLabel') and self.iconLabel:
                self.iconLabel.show()
                
            # Restore spacers to layout
            if hasattr(self, 'topSpacer') and self.topSpacer and self.dropFrame and self.dropFrame.layout():
                layout = self.dropFrame.layout()
                # Add top spacer back at index 0
                layout.insertItem(0, self.topSpacer)
                
            if hasattr(self, 'bottomSpacer') and self.bottomSpacer and self.dropFrame and self.dropFrame.layout():
                layout = self.dropFrame.layout()
                # Add bottom spacer back at the end
                layout.addItem(self.bottomSpacer)
                
            # Hide thumbnail label and show title label
            if hasattr(self, 'thumbnail_label'):
                self.thumbnail_label.hide()
                
            if hasattr(self, 'titleLabel') and self.titleLabel:
                # Restore original text and font
                self.titleLabel.setText(self.original_title_text)
                self.titleLabel.setFont(self.original_title_font)
                self.titleLabel.setAlignment(self.original_title_alignment)
                self.titleLabel.show()
                
            # Restore subtitle
            if self.subtitleLabel:
                self.subtitleLabel.setText("""
                Script ini hanya mengunggah gambar ke situs Picsart dan menggunakan fitur upscale otomatis di sana.

                Upscale tidak dilakukan oleh aplikasi ini, tapi oleh server Picsart.
                Hasil akan disimpan otomatis ke folder 'UPSCALE' sumber file asli. Fitur gratis Picsart hanya mendukung hingga 2x upscale. Gunakan seperlunya.
                """)
                
            # Force a layout update
            if self.dropFrame:
                self.dropFrame.updateGeometry()
                self.dropFrame.layout().activate()
                
        except Exception as e:
            logger.kesalahan("Error restoring title label", str(e))
            print(f"Error restoring title label: {e}")
    
    # Override window/widget events
    def resizeEvent(self, event):
        super().resizeEvent(event)
        # If we have an active thumbnail, update it to match the new window size
        if hasattr(self, 'thumbnail_label') and self.thumbnail_label.isVisible() and hasattr(self.thumbnail_label, 'updatePixmap'):
            self.thumbnail_label.updatePixmap()
    
    def closeEvent(self, event):
        """Handle when the window is closed"""
        # Stop any ongoing processing
        if hasattr(self, 'image_processor'):
            self.image_processor.stop_processing()
        
        # Reset UI buttons state
        self.reset_ui_buttons()
        
        event.accept()

def run_app(base_dir, icon_path=None):
    # Create Qt application
    app = QApplication(sys.argv)
    
    # Create main window
    window = SotongHDApp(base_dir, icon_path)
    
    # Start the event loop
    sys.exit(app.exec())