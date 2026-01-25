import os
import sys
from datetime import datetime
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QMessageBox, QProgressBar, 
                              QVBoxLayout, QLabel, QPushButton, QFileDialog,
                              QHBoxLayout, QGridLayout, QScrollArea, QSizePolicy, QTextEdit, QCheckBox, QSpinBox)
from PySide6.QtGui import QIcon, QPixmap, QDragEnterEvent, QDropEvent
from PySide6.QtCore import Qt, QTimer, QSize, QUrl, Signal, QObject
from PySide6.QtWidgets import QFrame, QSpacerItem
from pathlib import Path
import threading

from .background_process import ImageProcessor, ProgressSignal, FileUpdateSignal
from .frame_extractor import VideoFrameExtractor
from .video_upscaler_process import VideoUpscalerProcess
from .logger import logger
from .ui_helpers import (ScalableImageLabel, center_window_on_screen, setup_drag_drop_style, 
                       setup_format_toggle, set_application_icon)
from .progress_handler import ProgressHandler, ProgressUIManager
from .file_processor import (is_image_file, open_folder_dialog, open_files_dialog, 
                           open_whatsapp_group, show_statistics, confirm_stop_processing)
from .config_manager import ConfigManager
import json

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
        
        self.base_dir = base_dir
        
        self.original_title_text = "LEMPARKAN GAMBAR KE SINI!"
        
        if icon_path and os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            QApplication.setWindowIcon(QIcon(icon_path))
        else:
            logger.peringatan("Ikon aplikasi tidak ditemukan", icon_path)
        
        self.setGeometry(100, 100, 700, 700)
        self.setWindowTitle("SotongHD")

        center_window_on_screen(self)

        central_widget = QWidget(self)
        central_widget.setObjectName("centralwidget")
        main_vlayout = QVBoxLayout(central_widget)
        main_vlayout.setObjectName("verticalLayout_2")

        top_vlayout = QVBoxLayout()
        top_vlayout.setObjectName("verticalLayout")

        drop_frame = QFrame(central_widget)
        drop_frame.setObjectName("dropFrame")
        drop_frame.setFrameShape(QFrame.StyledPanel)
        drop_frame.setFrameShadow(QFrame.Raised)
        drop_frame.setStyleSheet("QFrame#dropFrame {\n  border: 2px dashed rgba(88, 29, 239, 0.08);\n  border-radius: 15px;\n  background-color: rgba(88, 29, 239, 0.08);\n}\n")

        drop_layout = QVBoxLayout(drop_frame)
        drop_layout.setObjectName("dropAreaLayout")

        self.topSpacer = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        drop_layout.addItem(self.topSpacer)

        self.iconLabel = QLabel(drop_frame)
        self.iconLabel.setObjectName("iconLabel")
        self.iconLabel.setMinimumSize(96, 96)
        possible_icon = os.path.join(base_dir, "sotonghd.ico")
        if os.path.exists(possible_icon):
            self.iconLabel.setPixmap(QPixmap(possible_icon))
        self.iconLabel.setAlignment(Qt.AlignCenter)
        drop_layout.addWidget(self.iconLabel, alignment=Qt.AlignCenter)

        self.titleLabel = QLabel("LEMPARKAN GAMBAR KE SINI!", drop_frame)
        self.titleLabel.setObjectName("titleLabel")
        title_font = self.titleLabel.font()
        title_font.setPointSize(20)
        title_font.setBold(True)
        self.titleLabel.setFont(title_font)
        self.titleLabel.setStyleSheet("color : rgba(138, 60, 226, 0.62);")
        self.titleLabel.setAlignment(Qt.AlignCenter)
        drop_layout.addWidget(self.titleLabel)

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

        self.bottomSpacer = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        drop_layout.addItem(self.bottomSpacer)

        top_vlayout.addWidget(drop_frame)
        main_vlayout.addLayout(top_vlayout)

        self.progress_bar = QProgressBar(central_widget)
        self.progress_bar.setObjectName("progressBar")
        self.progress_bar.setMinimumSize(0, 30)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Ready")
        self.progress_bar.setStyleSheet("QProgressBar {\n  border: none;\n  border-radius: 10px;\n  background-color: rgba(161, 161, 161, 0.08);\n  text-align: center;\n  font-weight: bold;\n  margin: 0px;\n  padding: 0px;\n  height: 30px;\n}\nQProgressBar::chunk {\n  background-color: #5720e3;\n  border-radius: 10px;\n}")
        main_vlayout.addWidget(self.progress_bar)

        controls_layout = QHBoxLayout()
        controls_layout.setObjectName("controlsLayout")

        self.batchLabel = QLabel("Batch:", central_widget)
        self.batchLabel.setObjectName("batchLabel")
        controls_layout.addWidget(self.batchLabel)

        from PySide6.QtWidgets import QSpinBox
        self.batchSpinner = QSpinBox(central_widget)
        self.batchSpinner.setObjectName("batchSpinner")
        self.batchSpinner.setMinimum(1)
        self.batchSpinner.setMaximum(10)
        self.batchSpinner.setValue(1)
        self.batchSpinner.setToolTip("Ukuran batch saat memproses file (1-10)")
        self.batchSpinner.setFixedWidth(80)
        controls_layout.addWidget(self.batchSpinner)

        controls_layout.addStretch()

        self.headlessCheck = QCheckBox("Headless", central_widget)
        self.headlessCheck.setObjectName("headlessCheck")
        self.headlessCheck.setChecked(True)
        self.headlessCheck.setToolTip("Jalankan browser dalam mode headless (True/False)")
        controls_layout.addWidget(self.headlessCheck)

        self.incognitoCheck = QCheckBox("Incognito", central_widget)
        self.incognitoCheck.setObjectName("incognitoCheck")
        self.incognitoCheck.setChecked(True)
        self.incognitoCheck.setToolTip("Jalankan browser dalam mode incognito (True/False)")
        controls_layout.addWidget(self.incognitoCheck)

        main_vlayout.addLayout(controls_layout)

        self.log_display = QTextEdit(central_widget)
        self.log_display.setObjectName("logDisplay")
        self.log_display.setMinimumSize(0, 100)
        self.log_display.setMaximumHeight(150)
        self.log_display.setReadOnly(True)
        self.log_display.setStyleSheet("QTextEdit {\n  border: none;\n  border-radius: 10px;\n  background-color: rgba(161, 161, 161, 0.08);\n  color: rgba(88, 29, 239, 0.7);\n  padding: 8px;\n  font-family: 'Consolas', monospace;\n  font-size: 9pt;\n}\n")
        main_vlayout.addWidget(self.log_display)

        buttons_layout = QHBoxLayout()
        buttons_layout.setObjectName("buttonsLayout")

        self.whatsappButton = QPushButton(central_widget)
        self.whatsappButton.setObjectName("whatsappButton")
        self.whatsappButton.setMinimumSize(40, 40)
        self.whatsappButton.setToolTip("Join WhatsApp Group")
        self.whatsappButton.setStyleSheet("QPushButton {\n  background-color: rgba(161, 161, 161, 0.08);\n  color: rgba(88, 29, 239, 0.7);\n  border-radius: 20px;\n  padding: 8px;\n}\nQPushButton:hover {\n  background-color: rgba(37, 211, 102, 0.8);\n  color: white;\n  border: none;\n}\nQPushButton:pressed {\n  background-color: rgba(37, 211, 102, 1.0);\n}")
        buttons_layout.addWidget(self.whatsappButton)

        self.chromeUpdateButton = QPushButton(central_widget)
        self.chromeUpdateButton.setObjectName("chromeUpdateButton")
        self.chromeUpdateButton.setMinimumSize(40, 40)
        self.chromeUpdateButton.setToolTip("Check Chrome Updates")
        self.chromeUpdateButton.setStyleSheet("QPushButton {\n  background-color: rgba(161, 161, 161, 0.08);\n  color: rgba(88, 29, 239, 0.7);\n  border-radius: 20px;\n  padding: 8px;\n}\nQPushButton:hover {\n  background-color: rgba(66, 133, 244, 0.8);\n  color: white;\n  border: none;\n}\nQPushButton:pressed {\n  background-color: rgba(66, 133, 244, 1.0);\n}")
        buttons_layout.addWidget(self.chromeUpdateButton)

        buttons_layout.addStretch()
        format_layout = QHBoxLayout()
        format_layout.setSpacing(4)

        self.formatToggle = QPushButton(central_widget)
        self.formatToggle.setObjectName("formatToggle")
        self.formatToggle.setMinimumSize(60, 30)
        self.formatToggle.setMaximumSize(60, 30)
        format_layout.addWidget(self.formatToggle)

        buttons_layout.addLayout(format_layout)
        buttons_layout.addStretch()

        self.stopButton = QPushButton("Stop", central_widget)
        self.stopButton.setObjectName("stopButton")
        self.stopButton.setEnabled(False)
        self.stopButton.setMinimumSize(90, 40)
        self.stopButton.setStyleSheet("QPushButton {\n  background-color: rgba(161, 161, 161, 0.08);\n  border-radius: 10px;\n  padding: 8px 16px;\n}\nQPushButton:hover {\n  background-color: rgba(231, 76, 60, 0.7);\n  color: white;\n  border: none;\n}\nQPushButton:pressed {\n  background-color: rgba(231, 76, 60, 1.0);\n}\nQPushButton:disabled {\n  background-color: rgba(161, 161, 161, 0.04);\n  color: rgba(161, 161, 161, 0.4);\n}")
        buttons_layout.addWidget(self.stopButton)

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

        self.setCentralWidget(central_widget)
        self.ui = central_widget
        
        self.setAcceptDrops(True)
        
        self.setup_ui_elements()
        self.setup_buttons()
        self.setup_thumbnail_label()
        self.setup_progress_handler()
        
        self.setup_image_processor(base_dir)
        
        if self.dropFrame:
            setup_drag_drop_style(self.dropFrame)
          
        self.show()
    
    def setup_ui_elements(self):
        self.dropFrame = getattr(self, 'dropFrame', None)
        if not self.dropFrame:
            self.dropFrame = self.findChild(QFrame, "dropFrame")
        self.iconLabel = getattr(self, 'iconLabel', self.findChild(QLabel, "iconLabel"))
        self.titleLabel = getattr(self, 'titleLabel', self.findChild(QLabel, "titleLabel"))
        self.subtitleLabel = getattr(self, 'subtitleLabel', self.findChild(QLabel, "subtitleLabel"))
        self.progress_bar = getattr(self, 'progress_bar', self.findChild(QProgressBar, "progressBar"))
        self.log_display = getattr(self, 'log_display', self.findChild(QTextEdit, "logDisplay"))
        
        
        if self.log_display:
            logger.set_log_widget(self.log_display)
            
        self.configure_size_policies()
        
        if self.iconLabel:
            self.setup_high_res_icon()
        
        self.formatToggle = self.findChild(QPushButton, "formatToggle")

        self.batchSpinner = getattr(self, 'batchSpinner', self.findChild(QSpinBox, "batchSpinner"))
        self.batchLabel = getattr(self, 'batchLabel', self.findChild(QLabel, "batchLabel"))
        self.headlessCheck = getattr(self, 'headlessCheck', self.findChild(QCheckBox, "headlessCheck"))
        self.incognitoCheck = getattr(self, 'incognitoCheck', self.findChild(QCheckBox, "incognitoCheck"))
        
        self.config_manager = ConfigManager(self.base_dir)
        try:
            batch_val = self.config_manager.get_batch_size()
            if hasattr(self, 'batchSpinner') and batch_val:
                self.batchSpinner.setValue(int(batch_val))

            headless_val = self.config_manager.get_headless()
            if hasattr(self, 'headlessCheck') and headless_val is not None:
                self.headlessCheck.setChecked(bool(headless_val))

            incognito_val = self.config_manager.get_incognito()
            if hasattr(self, 'incognitoCheck') and incognito_val is not None:
                self.incognitoCheck.setChecked(bool(incognito_val))
        except Exception:
            pass
        
        self.formatToggle = setup_format_toggle(self, self.config_manager)
    
    def setup_buttons(self):
        self.openFolderButton = self.findChild(QPushButton, "openFolderButton")
        self.openFilesButton = self.findChild(QPushButton, "openFilesButton")
        self.whatsappButton = self.findChild(QPushButton, "whatsappButton")
        self.chromeUpdateButton = self.findChild(QPushButton, "chromeUpdateButton")
        self.stopButton = self.findChild(QPushButton, "stopButton")
        
        if self.stopButton:
            self.stopButton.setEnabled(False)
            self.stopButton.clicked.connect(self.stop_processing)
        
        if qta:
            whatsapp_icon = qta.icon('fa5b.whatsapp')
            if self.whatsappButton:
                self.whatsappButton.setIcon(whatsapp_icon)
                self.whatsappButton.setIconSize(QSize(24, 24))
                self.whatsappButton.clicked.connect(self.on_whatsapp_button_click)
            
            chrome_icon = qta.icon('fa5b.chrome')
            if self.chromeUpdateButton:
                self.chromeUpdateButton.setIcon(chrome_icon)
                self.chromeUpdateButton.setIconSize(QSize(24, 24))
                self.chromeUpdateButton.clicked.connect(self.on_chrome_update_click)
            
            folder_icon = qta.icon('fa5s.folder-open')
            if self.openFolderButton:
                self.openFolderButton.setIcon(folder_icon)
                self.openFolderButton.setIconSize(QSize(16, 16))
                self.openFolderButton.clicked.connect(self.on_open_folder_click)
            
            files_icon = qta.icon('fa5s.file-image')
            if self.openFilesButton:
                self.openFilesButton.setIcon(files_icon)
                self.openFilesButton.setIconSize(QSize(16, 16))
                self.openFilesButton.clicked.connect(self.on_open_files_click)
            
            stop_icon = qta.icon('fa5s.stop')
            if self.stopButton:
                self.stopButton.setIcon(stop_icon)
                self.stopButton.setIconSize(QSize(16, 16))
        else:
            if self.whatsappButton:
                self.whatsappButton.setText("WA")
                self.whatsappButton.clicked.connect(self.on_whatsapp_button_click)
            
            if self.chromeUpdateButton:
                self.chromeUpdateButton.setText("Chr")
                self.chromeUpdateButton.clicked.connect(self.on_chrome_update_click)
            
            if self.openFolderButton:
                self.openFolderButton.clicked.connect(self.on_open_folder_click)
                
            if self.openFilesButton:
                self.openFilesButton.clicked.connect(self.on_open_files_click)

        try:
            if hasattr(self, 'batchSpinner') and self.batchSpinner:
                self.batchSpinner.valueChanged.connect(lambda v: self.config_manager.set_batch_size(int(v)))

            if hasattr(self, 'headlessCheck') and self.headlessCheck:
                self.headlessCheck.stateChanged.connect(lambda s: self.config_manager.set_headless(bool(self.headlessCheck.isChecked())))

            if hasattr(self, 'incognitoCheck') and self.incognitoCheck:
                self.incognitoCheck.stateChanged.connect(lambda s: self.config_manager.set_incognito(bool(self.incognitoCheck.isChecked())))
        except Exception:
            pass
    
    def setup_thumbnail_label(self):
        self.thumbnail_label = ScalableImageLabel()
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.hide()
        self.thumbnail_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        if self.titleLabel:
            self.original_title_font = self.titleLabel.font()
            self.original_title_text = self.titleLabel.text()
            self.original_title_alignment = self.titleLabel.alignment()
            
            parent_layout = self.titleLabel.parentWidget().layout()
            title_index = parent_layout.indexOf(self.titleLabel)
            
            if title_index >= 0:
                parent_layout.insertWidget(title_index, self.thumbnail_label)
    
    def setup_progress_handler(self):
        self.progress_handler = ProgressHandler(self)
        
        self.progress_ui_manager = ProgressUIManager(self.progress_bar)
        
        self.current_image = None
    
    def setup_image_processor(self, base_dir):
        try:
            driver_filename = 'chromedriver.exe' if sys.platform == 'win32' else 'chromedriver'
            chromedriver_path = os.path.abspath(os.path.join(base_dir, "driver", driver_filename))
            
            if not os.path.exists(chromedriver_path):
                error_msg = f"ChromeDriver not found at: {chromedriver_path}\n"
                error_msg += f"Base directory: {base_dir}\n"
                error_msg += "Please run main.py first to download ChromeDriver."
                logger.kesalahan("ChromeDriver tidak ditemukan", chromedriver_path)
                print(error_msg)
                raise FileNotFoundError(error_msg)
            

            if sys.platform != 'win32':
                import stat
                current_permissions = os.stat(chromedriver_path).st_mode
                if not (current_permissions & stat.S_IXUSR):
                    logger.info(f"Making chromedriver executable: {chromedriver_path}")
                    try:
                        os.chmod(chromedriver_path, current_permissions | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                    except Exception as e:
                        logger.peringatan(f"Could not set executable permission: {e}")
            

            
            self.progress_signal = ProgressSignal()
            self.progress_signal.progress.connect(self.progress_handler.handle_progress)
            
            self.file_update_signal = FileUpdateSignal()
            self.file_update_signal.file_update.connect(self.progress_handler.handle_file_update)
            
            self.image_processor = ImageProcessor(
                chromedriver_path=chromedriver_path,
                progress_signal=self.progress_signal,
                file_update_signal=self.file_update_signal,
                config_manager=self.config_manager,
                headless=(bool(self.headlessCheck.isChecked()) if hasattr(self, 'headlessCheck') else None),
                incognito=(bool(self.incognitoCheck.isChecked()) if hasattr(self, 'incognitoCheck') else None)
            )
            if hasattr(self, 'batchSpinner') and self.batchSpinner:
                self.image_processor.batch_size = int(self.batchSpinner.value())
            logger.sukses("Aplikasi SotongHD siap digunakan")
            logger.info("Untuk memulai, seret dan lepas gambar atau folder ke area drop")
        except Exception as e:
            logger.kesalahan("Gagal menginisialisasi image processor", str(e))
            QMessageBox.critical(self, "Error", f"Gagal menginisialisasi processor: {str(e)}")
    
    def setup_high_res_icon(self):
        possible_paths = [
            self.windowIcon().name(),
            os.path.join(self.base_dir, "sotonghd.ico"),
            os.path.join(self.base_dir, "App", "sotonghd.ico"),
            os.path.join(self.base_dir, "App", "sotong_bg.png")
        ]
        
        for path in possible_paths:
            if path and os.path.exists(path):
                if set_application_icon(self, path):
                    break
        else:
            logger.peringatan("Tidak dapat menemukan ikon aplikasi")
    
    def configure_size_policies(self):
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        central_widget = self.centralWidget()
        if central_widget:
            central_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            
        if self.dropFrame:
            self.dropFrame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            
            parent_layout = None
            if self.dropFrame.parent() and self.dropFrame.parent().layout():
                parent_layout = self.dropFrame.parent().layout()
                for i in range(parent_layout.count()):
                    parent_layout.setStretch(i, 1)
            
            if self.dropFrame.layout():
                layout = self.dropFrame.layout()
                layout.setStretch(0, 1)
                layout.setStretch(4, 1)
        
        if self.titleLabel:
            self.titleLabel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        
        if self.subtitleLabel:
            self.subtitleLabel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        mime_data = event.mimeData()
        if mime_data and mime_data.hasUrls():
            has_local_files = any(url.isLocalFile() for url in mime_data.urls())
            if has_local_files:
                event.acceptProposedAction()
                setup_drag_drop_style(self.dropFrame, highlighted=True)
                return
        event.ignore()
        
    def dragLeaveEvent(self, event):
        setup_drag_drop_style(self.dropFrame)
        
    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            
    def dropEvent(self, event: QDropEvent):
        setup_drag_drop_style(self.dropFrame)
        
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            
            file_paths = []
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                file_paths.append(file_path)
            
            if file_paths:
                paths_str = ", ".join([os.path.basename(p) for p in file_paths])
                logger.info(f"File diterima: {len(file_paths)} item", paths_str)
                self.process_files(file_paths)
    
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
    
    def on_chrome_update_click(self):
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.chrome.options import Options
            import tempfile
            
            logger.info(f"Base directory: {self.base_dir}")
            
            driver_filename = 'chromedriver.exe' if sys.platform == 'win32' else 'chromedriver'
            chromedriver_path = os.path.abspath(os.path.join(self.base_dir, "driver", driver_filename))
            
            logger.info(f"Mencari ChromeDriver di: {chromedriver_path}")
            
            if not os.path.exists(chromedriver_path):
                driver_folder = os.path.join(self.base_dir, "driver")
                if os.path.exists(driver_folder):
                    contents = os.listdir(driver_folder)
                    logger.info(f"Isi folder driver: {contents}")
                else:
                    logger.kesalahan("Folder driver tidak ditemukan", driver_folder)
                
                error_msg = f"ChromeDriver tidak ditemukan di: {chromedriver_path}"
                logger.kesalahan("ChromeDriver tidak ditemukan", chromedriver_path)
                QMessageBox.critical(self, "Error", f"{error_msg}\n\nPastikan file {driver_filename} ada di folder driver/")
                return
            
            if sys.platform != 'win32':
                import stat
                current_permissions = os.stat(chromedriver_path).st_mode
                if not (current_permissions & stat.S_IXUSR):
                    logger.info(f"Making chromedriver executable: {chromedriver_path}")
                    try:
                        os.chmod(chromedriver_path, current_permissions | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                    except Exception as e:
                        logger.peringatan(f"Could not set executable permission: {e}")
            
            chrome_options = Options()
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1024,768")
            chrome_options.add_argument("--log-level=3")
            chrome_options.add_argument("--profile-directory=Default")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            temp_user_data = tempfile.mkdtemp(prefix="chrome_temp_")
            chrome_options.add_argument(f"--user-data-dir={temp_user_data}")
            
            logger.info(f"Menggunakan ChromeDriver: {chromedriver_path}")
            logger.info("Membuka Chrome untuk cek update")
            
            service = Service(executable_path=chromedriver_path)
            
            old_path = os.environ.get('PATH', '')
            try:
                new_path_parts = []
                for part in old_path.split(os.pathsep):
                    if 'webdriver' not in part.lower() and 'chromedriver' not in part.lower():
                        new_path_parts.append(part)
                os.environ['PATH'] = os.pathsep.join(new_path_parts)
                
                driver = webdriver.Chrome(service=service, options=chrome_options)
                
                driver.get("chrome://settings/help")
                
                logger.sukses("Chrome berhasil dibuka untuk cek update")
                
            finally:
                os.environ['PATH'] = old_path
            
        except FileNotFoundError as e:
            error_msg = f"ChromeDriver tidak ditemukan: {str(e)}"
            logger.kesalahan("ChromeDriver file tidak ada", error_msg)
            QMessageBox.critical(self, "Error", f"{error_msg}\n\nDownload ulang aplikasi atau pastikan folder driver/ lengkap.")
        except Exception as e:
            logger.kesalahan("Gagal membuka Chrome untuk cek update", str(e))
            QMessageBox.warning(self, "Error", f"Gagal membuka Chrome: {str(e)}\n\nPastikan Chrome terinstall di sistem.")
    
    def process_files(self, file_paths):
        self.restore_title_label()
        paths_str = ", ".join([os.path.basename(p) for p in file_paths])
        logger.info(f"Memproses {len(file_paths)} item", paths_str)
        
        if self.stopButton:
            self.stopButton.setEnabled(True)
        
        if self.openFolderButton:
            self.openFolderButton.setEnabled(False)
        if self.openFilesButton:
            self.openFilesButton.setEnabled(False)
        
        if hasattr(self, 'image_processor'):
            try:
                if hasattr(self, 'batchSpinner'):
                    val = int(self.batchSpinner.value())
                    self.config_manager.set_batch_size(val)
                    self.image_processor.batch_size = val

                if hasattr(self, 'headlessCheck'):
                    h = bool(self.headlessCheck.isChecked())
                    self.config_manager.set_headless(h)
                    self.image_processor.headless = h
                else:
                    self.image_processor.headless = None

                if hasattr(self, 'incognitoCheck'):
                    inc = bool(self.incognitoCheck.isChecked())
                    self.config_manager.set_incognito(inc)
                    self.image_processor.incognito = inc
                else:
                    self.image_processor.incognito = None
            except Exception:
                pass

        video_exts = {'.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v'}
        video_files = [p for p in file_paths if Path(p).suffix.lower() in video_exts and Path(p).is_file()]
        if video_files:
            self.start_video_extraction(video_files)
            return

        self.image_processor.start_processing(file_paths)
        
        self.check_processor_thread()
    
    def check_processor_thread(self):
        """Cek status thread pemrosesan dan tampilkan statistik jika selesai"""
        if not self.image_processor.processing_thread or not self.image_processor.processing_thread.is_alive():
            if self.image_processor.end_time:
                stats = self.image_processor.get_statistics()
                show_statistics(self, stats)
            
            self.reset_ui_buttons()
        else:
            QApplication.processEvents()
            QTimer.singleShot(100, self.check_processor_thread)

    def start_video_extraction(self, video_files):
        if not hasattr(self, 'progress_signal') or self.progress_signal is None:
            self.progress_signal = ProgressSignal()
            self.progress_signal.progress.connect(self.progress_handler.handle_progress)

        out_root = os.path.join(self.base_dir, 'temp', 'video_upscale')
        os.makedirs(out_root, exist_ok=True)
        logger.info("Video upscale temp root:", out_root)

        logger.info(f"Mulai ekstrak frame dari {len(video_files)} video(s)")

        self.video_extractor = VideoFrameExtractor(self.base_dir, progress_signal=self.progress_signal)
        self.video_thread = threading.Thread(target=self._run_extraction_thread, args=(self.video_extractor, video_files, out_root))
        self.video_thread.daemon = True
        self.video_thread.start()

        self.check_video_thread()

    def _run_extraction_thread(self, extractor, video_paths, out_root):
        # Collect stats per video and aggregate at the end to show a single dialog
        video_stats_list = []

        for video_path in video_paths:
            out_dir = None
            try:
                logger.info(f"Ekstrak: {video_path}")
                out_dir = extractor.extract_frames(video_path, out_root)
            except Exception as e:
                logger.kesalahan("Ekstraksi frame gagal", str(e))
                print(f"Error: Ekstraksi frame gagal untuk {video_path}: {e}")
                # derive expected UPSCALE folder from source video path
                expected_upscale = None
                try:
                    expected_upscale = str(Path(video_path).parent / 'UPSCALE')
                except Exception:
                    expected_upscale = str(video_path)
                # record a deterministic failure stat for this video
                video_stats_list.append({
                    'total_processed': 0,
                    'total_failed': 0,
                    'total_duration': 0,
                    'start_time': None,
                    'end_time': None,
                    'results': [],
                    'processed_folders': [expected_upscale],
                })
                continue

            driver_filename = 'chromedriver.exe' if sys.platform == 'win32' else 'chromedriver'
            chromedriver_path = os.path.abspath(os.path.join(self.base_dir, "driver", driver_filename))

            if not os.path.exists(chromedriver_path):
                logger.kesalahan("ChromeDriver tidak ditemukan untuk proses upscale video", chromedriver_path)
                print(f"Error: ChromeDriver tidak ditemukan: {chromedriver_path}")
                video_stats_list.append({
                    'total_processed': 0,
                    'total_failed': 0,
                    'total_duration': 0,
                    'start_time': None,
                    'end_time': None,
                    'results': [],
                    'processed_folders': [str(out_dir) if out_dir is not None else str(video_path)],
                })
                continue

            headless = (bool(self.headlessCheck.isChecked()) if hasattr(self, 'headlessCheck') else None)
            incognito = (bool(self.incognitoCheck.isChecked()) if hasattr(self, 'incognitoCheck') else None)

            self.video_upscaler = VideoUpscalerProcess(
                base_dir=self.base_dir,
                chromedriver_path=chromedriver_path,
                config_manager=self.config_manager,
                headless=headless,
                incognito=incognito,
                progress_signal=getattr(self, 'progress_signal', None)
            )

            # capture local reference to avoid race with stop/reset
            upscaler = self.video_upscaler

            try:
                upscaler.upscale_hash_sync(out_dir)
                # use local reference for stats collection to avoid NoneType if self.video_upscaler is cleared elsewhere
                if not getattr(upscaler, 'processor', None):
                    logger.kesalahan("Upscaler missing processor after run", str(out_dir))
                    print(f"Error: Upscaler has no processor for {out_dir}")
                    video_stats_list.append({
                        'total_processed': 0,
                        'total_failed': 0,
                        'total_duration': 0,
                        'start_time': None,
                        'end_time': None,
                        'results': [],
                        'processed_folders': [str(Path(video_path).parent / 'UPSCALE')],
                    })
                else:
                    stats = upscaler.processor.get_statistics()

                    # map processed_folders to UPSCALE folder(s) of the source video
                    meta_path = Path(out_dir) / 'meta.json'
                    upscale_folder = None
                    if meta_path.exists():
                        with open(meta_path, 'r', encoding='utf-8') as mf:
                            try:
                                meta = json.load(mf)
                                src_vid = meta.get('source_video')
                                if src_vid:
                                    upscale_folder = str(Path(src_vid).parent / 'UPSCALE')
                            except Exception as e:
                                logger.kesalahan("Gagal membaca meta untuk menentukan UPSCALE folder", str(e))
                                print(f"Error reading meta.json for {out_dir}: {e}")
                    if not upscale_folder:
                        upscale_folder = str(Path(video_path).parent / 'UPSCALE')

                    stats['processed_folders'] = [upscale_folder]
                    print(f"Video processed: {video_path} - Success: {stats.get('total_processed')}, Failed: {stats.get('total_failed')}")
                    logger.info(f"Video upscale completed", str(out_dir))
                    video_stats_list.append(stats)
            except Exception as e:
                logger.kesalahan("Upscale video gagal", str(e))
                print(f"Error: Upscale video gagal untuk {out_dir}: {e}")
                # attempt to gather stats, if available; if not, record deterministic failure stat
                upscale_folder = None
                try:
                    meta_path = Path(out_dir) / 'meta.json'
                    if meta_path.exists():
                        with open(meta_path, 'r', encoding='utf-8') as mf:
                            meta = json.load(mf)
                            src_vid = meta.get('source_video')
                            if src_vid:
                                upscale_folder = str(Path(src_vid).parent / 'UPSCALE')
                except Exception as inner_e:
                    logger.kesalahan("Gagal membaca meta.json setelah kegagalan", str(inner_e))
                    print(f"Error reading meta.json during failure handling: {inner_e}")

                if not upscale_folder:
                    upscale_folder = str(Path(video_path).parent / 'UPSCALE')

                if upscaler and getattr(upscaler, 'processor', None):
                    try:
                        stats = upscaler.processor.get_statistics()
                        stats['processed_folders'] = [upscale_folder]
                        video_stats_list.append(stats)
                    except Exception as inner_e:
                        logger.kesalahan("Gagal mengambil statistik setelah kegagalan", str(inner_e))
                        print(f"Error collecting stats after failure: {inner_e}")
                        video_stats_list.append({
                            'total_processed': 0,
                            'total_failed': 0,
                            'total_duration': 0,
                            'start_time': None,
                            'end_time': None,
                            'results': [],
                            'processed_folders': [upscale_folder],
                        })
                else:
                    video_stats_list.append({
                        'total_processed': 0,
                        'total_failed': 0,
                        'total_duration': 0,
                        'start_time': None,
                        'end_time': None,
                        'results': [],
                        'processed_folders': [upscale_folder],
                    })
            finally:
                # clear instance reference on self; local 'upscaler' retains the instance
                self.video_upscaler = None

        # aggregate stats across all videos and store for UI thread
        if video_stats_list:
            total_processed = sum(v.get('total_processed', 0) for v in video_stats_list)
            total_failed = sum(v.get('total_failed', 0) for v in video_stats_list)
            total_duration = sum(v.get('total_duration', 0) for v in video_stats_list)

            start_times = [v.get('start_time') for v in video_stats_list if v.get('start_time')]
            end_times = [v.get('end_time') for v in video_stats_list if v.get('end_time')]
            agg_start = min(start_times) if start_times else None
            agg_end = max(end_times) if end_times else None

            processed_folders = []
            results = []
            for v in video_stats_list:
                processed_folders.extend(v.get('processed_folders', []))
                results.extend(v.get('results', []))

            # For video batches, display counts per VIDEO (not per frame)
            video_success_count = sum(1 for v in video_stats_list if v.get('total_processed', 0) > 0 and v.get('total_failed', 0) == 0)
            video_failure_count = len(video_stats_list) - video_success_count

            # Deduplicate processed_folders and keep order
            seen = set()
            uniq_folders = []
            for p in processed_folders:
                if p not in seen:
                    seen.add(p)
                    uniq_folders.append(p)

            aggregated = {
                'total_processed': video_success_count,
                'total_failed': video_failure_count,
                'total_duration': total_duration,
                'start_time': agg_start,
                'end_time': agg_end,
                'results': results,
                'processed_folders': uniq_folders,
            }

            print(f"All videos processed: total_success={total_processed}, total_failed={total_failed}")
            logger.info("All videos processed", f"success={total_processed}, failed={total_failed}")
            self.last_video_stats = aggregated

        return

    def check_video_thread(self):
        if hasattr(self, 'video_thread') and self.video_thread is not None and self.video_thread.is_alive():
            QApplication.processEvents()
            QTimer.singleShot(200, self.check_video_thread)
            return

        # finished or not started
        if hasattr(self, 'video_extractor') and self.video_extractor is not None:
            logger.sukses("Ekstraksi video selesai atau dihentikan")
        # If a video finished, show stats dialog (UI thread)
        if hasattr(self, 'last_video_stats') and self.last_video_stats:
            try:
                show_statistics(self, self.last_video_stats)
            finally:
                self.last_video_stats = None

        self.video_extractor = None
        self.video_thread = None
        self.reset_ui_buttons()
    
    def stop_processing(self):
        """Hentikan pemrosesan dan reset UI"""
        logger.info("Menghentikan pemrosesan atas permintaan user")
        
        if confirm_stop_processing(self):
            if hasattr(self, 'image_processor'):
                self.image_processor.stop_processing()
            if hasattr(self, 'video_extractor') and getattr(self, 'video_extractor') is not None:
                logger.info("Menghentikan ekstraksi video atas permintaan user")
                self.video_extractor.stop()
                if hasattr(self, 'video_thread') and self.video_thread is not None and self.video_thread.is_alive():
                    self.video_thread.join(5)
                self.video_extractor = None
                self.video_thread = None

            if hasattr(self, 'video_upscaler') and getattr(self, 'video_upscaler') is not None:
                logger.info("Menghentikan proses upscale video atas permintaan user")
                try:
                    self.video_upscaler.stop()
                    if getattr(self.video_upscaler, 'thread', None) and self.video_upscaler.thread.is_alive():
                        self.video_upscaler.thread.join(10)
                except Exception as e:
                    logger.kesalahan("Gagal menghentikan upscaler", str(e))
                self.video_upscaler = None
            
            self.restore_title_label()
            self.reset_ui_buttons()
            
            if self.progress_bar:
                self.progress_bar.setValue(0)
                self.progress_bar.setFormat("Proses dibatalkan oleh user")
            
            logger.peringatan("Proses dibatalkan oleh user")
    
    def reset_ui_buttons(self):
        if self.stopButton:
            self.stopButton.setEnabled(False)
        
        if self.openFolderButton:
            self.openFolderButton.setEnabled(True)
        if self.openFilesButton:
            self.openFilesButton.setEnabled(True)
    
    def update_progress(self, message, percentage=None):
        self.progress_ui_manager.update_progress(message, percentage)

    def update_thumbnail(self, file_path):
        if not file_path or not os.path.exists(file_path):
            logger.peringatan("Thumbnail tidak dapat ditampilkan, file tidak ditemukan", file_path)
            return
            
        try:
            if hasattr(self, 'iconLabel') and self.iconLabel:
                self.iconLabel.hide()
                
            if hasattr(self, 'topSpacer') and self.topSpacer and self.dropFrame and self.dropFrame.layout():
                layout = self.dropFrame.layout()
                layout.removeItem(self.topSpacer)
                
            if hasattr(self, 'bottomSpacer') and self.bottomSpacer and self.dropFrame and self.dropFrame.layout():
                layout = self.dropFrame.layout()
                layout.removeItem(self.bottomSpacer)
                
            if hasattr(self, 'thumbnail_label'):
                self.thumbnail_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                self.thumbnail_label.setMinimumHeight(300)
                
            if hasattr(self, 'titleLabel') and self.titleLabel:
                self.titleLabel.hide()
                self.thumbnail_label.show()
                
                parent_layout = self.titleLabel.parentWidget().layout()
                if parent_layout:
                    title_index = parent_layout.indexOf(self.thumbnail_label)
                    if title_index >= 0:
                        parent_layout.setStretch(title_index, 10)

                success = self.thumbnail_label.setImagePath(file_path)

                if not success:
                    logger.peringatan("Gagal memuat thumbnail", file_path)
                    self.restore_title_label()
                    return
                    
                file_name = os.path.basename(file_path)
                if self.subtitleLabel:
                    self.subtitleLabel.setText(f"Memproses: {file_name}")
                    
            if self.dropFrame:
                self.dropFrame.updateGeometry()
                self.dropFrame.layout().activate()
                
        except Exception as e:
            logger.kesalahan("Error menampilkan thumbnail", f"{file_path} - {str(e)}")
            print(f"Error showing thumbnail: {e}")
            self.restore_title_label()
    
    def restore_title_label(self):
        """Restore the title label to its original state"""
        try:
            if hasattr(self, 'iconLabel') and self.iconLabel:
                self.iconLabel.show()
                
            if hasattr(self, 'topSpacer') and self.topSpacer and self.dropFrame and self.dropFrame.layout():
                layout = self.dropFrame.layout()
                layout.insertItem(0, self.topSpacer)
                
            if hasattr(self, 'bottomSpacer') and self.bottomSpacer and self.dropFrame and self.dropFrame.layout():
                layout = self.dropFrame.layout()
                layout.addItem(self.bottomSpacer)
                
            if hasattr(self, 'thumbnail_label'):
                self.thumbnail_label.hide()
                
            if hasattr(self, 'titleLabel') and self.titleLabel:
                self.titleLabel.setText(self.original_title_text)
                self.titleLabel.setFont(self.original_title_font)
                self.titleLabel.setAlignment(self.original_title_alignment)
                self.titleLabel.show()
                
            if self.subtitleLabel:
                self.subtitleLabel.setText("""
                Script ini hanya mengunggah gambar ke situs Picsart dan menggunakan fitur upscale otomatis di sana.

                Upscale tidak dilakukan oleh aplikasi ini, tapi oleh server Picsart.
                Hasil akan disimpan otomatis ke folder 'UPSCALE' sumber file asli. Fitur gratis Picsart hanya mendukung hingga 2x upscale. Gunakan seperlunya.
                """)
                
            if self.dropFrame:
                self.dropFrame.updateGeometry()
                self.dropFrame.layout().activate()
                
        except Exception as e:
            logger.kesalahan("Error restoring title label", str(e))
            print(f"Error restoring title label: {e}")
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'thumbnail_label') and self.thumbnail_label.isVisible() and hasattr(self.thumbnail_label, 'updatePixmap'):
            self.thumbnail_label.updatePixmap()
    
    def closeEvent(self, event):
        if hasattr(self, 'image_processor'):
            self.image_processor.stop_processing()
        
        self.reset_ui_buttons()
        
        event.accept()

def run_app(base_dir, icon_path=None):
    app = QApplication(sys.argv)
    
    window = SotongHDApp(base_dir, icon_path)
    
    sys.exit(app.exec())