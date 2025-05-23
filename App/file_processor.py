import os
from PySide6.QtWidgets import QMessageBox, QFileDialog
from PySide6.QtGui import QImageReader, QDesktopServices
from PySide6.QtCore import QUrl
from .logger import logger
from .dialogs import StatsDialog

def is_image_file(file_path):
    """Check if the file is a valid image that can be loaded"""
    if not os.path.isfile(file_path):
        return False
        
    # Check if it's a supported image format
    reader = QImageReader(file_path)
    return reader.canRead()

def open_folder_dialog(parent):
    """Open a file dialog to select folders to process"""
    folder_path = QFileDialog.getExistingDirectory(
        parent,
        "Select Folder with Images",
        os.path.expanduser("~"),
        QFileDialog.ShowDirsOnly
    )
    
    if folder_path:
        logger.info("Folder dipilih", folder_path)
        return folder_path
    return None

def open_files_dialog(parent):
    """Open a file dialog to select multiple image files to process"""
    file_paths, _ = QFileDialog.getOpenFileNames(
        parent,
        "Select Images",
        os.path.expanduser("~"),
        "Image Files (*.jpg *.jpeg *.png *.bmp *.gif);;All Files (*)"
    )
    
    if file_paths:
        logger.info(f"File dipilih: {len(file_paths)} item")
        return file_paths
    return []

def open_whatsapp_group(group_url="https://chat.whatsapp.com/CMQvDxpCfP647kBBA6dRn3"):
    """Opens the WhatsApp group link in the default browser"""
    QDesktopServices.openUrl(QUrl(group_url))

def show_statistics(parent, stats):
    """Tampilkan dialog statistik"""
    logger.info("Statistik proses", f"Berhasil: {stats['total_processed']}, Gagal: {stats['total_failed']}")
    
    # Make sure processed_folders exists in stats
    if 'processed_folders' not in stats:
        stats['processed_folders'] = []
    
    dialog = StatsDialog(parent, stats)
    dialog.exec()

def confirm_stop_processing(parent):
    """Show confirmation dialog for stopping processing"""
    reply = QMessageBox.question(
        parent, 
        "Konfirmasi Pembatalan", 
        "Apakah Anda yakin ingin menghentikan proses?",
        QMessageBox.Yes | QMessageBox.No, 
        QMessageBox.No
    )
    return reply == QMessageBox.Yes
