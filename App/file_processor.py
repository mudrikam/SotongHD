import os
from PySide6.QtWidgets import QMessageBox, QFileDialog
from PySide6.QtGui import QImageReader, QDesktopServices
from PySide6.QtCore import QUrl
from .logger import logger
from .dialogs import StatsDialog

def is_image_file(file_path):
    if not os.path.isfile(file_path):
        return False
    reader = QImageReader(file_path)
    return reader.canRead()

def open_folder_dialog(parent):
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
    QDesktopServices.openUrl(QUrl(group_url))

def show_statistics(parent, stats):
    logger.info("Statistik proses", f"Berhasil: {stats['total_processed']}, Gagal: {stats['total_failed']}")
    if 'processed_folders' not in stats:
        stats['processed_folders'] = []
    dialog = StatsDialog(parent, stats)
    dialog.exec()

def confirm_stop_processing(parent):
    reply = QMessageBox.question(
        parent, 
        "Konfirmasi Pembatalan", 
        "Apakah Anda yakin ingin menghentikan proses?",
        QMessageBox.Yes | QMessageBox.No, 
        QMessageBox.No
    )
    return reply == QMessageBox.Yes
