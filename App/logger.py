import os
import sys
import logging
from datetime import datetime
from pathlib import Path
from PySide6.QtWidgets import QTextEdit
from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtGui import QTextCursor  # Import QTextCursor for cursor operations

# Add a UI logging signal for the TextEdit widget
class LogUISignal(QObject):
    log_message = Signal(str, str)  # Signal with formatted message and level

class SotongLogger:
    """Logger untuk aplikasi SotongHD yang menampilkan pesan dalam format yang ramah pengguna."""
    
    # Konstanta untuk level log yang lebih ramah pengguna
    INFO = 0
    SUKSES = 1
    PERINGATAN = 2
    KESALAHAN = 3
    DEBUG = 4
    
    # Warna untuk terminal jika didukung
    WARNA = {
        'reset': '\033[0m',
        'hijau': '\033[92m',
        'kuning': '\033[93m',
        'merah': '\033[91m',
        'biru': '\033[94m',
        'ungu': '\033[95m'
    }
    
    # Warna untuk UI log display (HTML)
    HTML_WARNA = {
        'info': "#3498db",      # Biru
        'sukses': "#2ecc71",    # Hijau
        'peringatan': "#f39c12", # Kuning
        'kesalahan': "#e74c3c", # Merah
        'debug': "#9b59b6"      # Ungu
    }
    
    def __init__(self, log_folder=None, console_output=True, file_output=True, level=0):
        """
        Inisialisasi logger SotongHD
        
        Args:
            log_folder: Folder untuk menyimpan log. Default adalah folder Logs di folder aplikasi
            console_output: Apakah output ke konsol (True/False)
            file_output: Apakah output ke file (True/False)
            level: Level log minimum (0=INFO, 1=SUKSES, 2=PERINGATAN, 3=KESALAHAN, 4=DEBUG)
        """
        self.console_output = console_output
        self.file_output = file_output
        self.level = level
        self.log_ui_signal = LogUISignal()
        self.ui_initialized = False
        self.log_widget = None
        
        # Periksa apakah terminal mendukung warna
        self.warna_didukung = sys.stdout.isatty()
        
        # Buat folder log jika perlu
        if file_output:
            if log_folder is None:
                # Default folder log
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                log_folder = os.path.join(base_dir, "Logs")
            
            os.makedirs(log_folder, exist_ok=True)
            
            # Siapkan file log dengan tanggal
            tanggal_sekarang = datetime.now().strftime("%Y-%m-%d")
            self.log_file = os.path.join(log_folder, f"sotonghd_{tanggal_sekarang}.log")
    
    def set_log_widget(self, widget: QTextEdit):
        """Set widget target untuk UI logging"""
        self.log_widget = widget
        self.ui_initialized = True
        self.log_ui_signal.log_message.connect(self._update_log_widget)
        
        # Set font dan style
        widget.document().setMaximumBlockCount(500)  # Batasi jumlah baris
    
    def _update_log_widget(self, message: str, level: str):
        """Update UI text edit widget (dipanggil via signal/slot untuk thread safety)"""
        if not self.log_widget:
            return
            
        # Format pesan dengan warna HTML berdasarkan level
        color = self.HTML_WARNA.get(level.lower(), "#000000")
        
        # Tambahkan pesan ke text edit (diformat dengan HTML)
        html_message = f'<span style="color:{color};">{message}</span><br>'
        self.log_widget.insertHtml(html_message)
        
        # Auto-scroll ke bawah - use QTextCursor instead of deprecated Qt.MoveOperation
        cursor = self.log_widget.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_widget.setTextCursor(cursor)
        self.log_widget.ensureCursorVisible()
    
    def _log(self, level, pesan, detail=None):
        """
        Fungsi internal untuk mencatat log
        
        Args:
            level: Level log (INFO, SUKSES, dll)
            pesan: Pesan utama
            detail: Detail tambahan (opsional)
        """
        if level < self.level:
            return
            
        # Format timestamp
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Tentukan prefix berdasarkan level
        level_text = ""
        warna = self.WARNA['reset']
        level_name = ""
        
        if level == self.INFO:
            level_text = "INFO"
            warna = self.WARNA['biru']
            level_name = "info"
        elif level == self.SUKSES:
            level_text = "SUKSES"
            warna = self.WARNA['hijau']
            level_name = "sukses"
        elif level == self.PERINGATAN:
            level_text = "PERINGATAN"
            warna = self.WARNA['kuning']
            level_name = "peringatan"
        elif level == self.KESALAHAN:
            level_text = "KESALAHAN"
            warna = self.WARNA['merah']
            level_name = "kesalahan"
        elif level == self.DEBUG:
            level_text = "DEBUG"
            warna = self.WARNA['ungu']
            level_name = "debug"
            
        # Format pesan
        log_message = f"[{timestamp}] {level_text}: {pesan}"
        if detail:
            log_message += f" - {detail}"
            
        # Output ke konsol dengan warna jika didukung
        if self.console_output:
            if self.warna_didukung:
                print(f"{warna}{log_message}{self.WARNA['reset']}")
            else:
                print(log_message)
                
        # Tulis ke file tanpa kode warna
        if self.file_output:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_message + "\n")
                
        # Kirim ke UI log widget jika tersedia
        if self.ui_initialized:
            self.log_ui_signal.log_message.emit(log_message, level_name)
    
    def info(self, pesan, detail=None):
        """Log informasi umum"""
        self._log(self.INFO, pesan, detail)
    
    def sukses(self, pesan, detail=None):
        """Log untuk operasi yang berhasil"""
        self._log(self.SUKSES, pesan, detail)
        
    def peringatan(self, pesan, detail=None):
        """Log untuk peringatan"""
        self._log(self.PERINGATAN, pesan, detail)
        
    def kesalahan(self, pesan, detail=None):
        """Log untuk kesalahan"""
        self._log(self.KESALAHAN, pesan, detail)
        
    def debug(self, pesan, detail=None):
        """Log untuk informasi debugging"""
        self._log(self.DEBUG, pesan, detail)
    
    def log_operasi_file(self, tipe_operasi, file_path, sukses=True, detail=None):
        """
        Fungsi khusus untuk mencatat operasi yang berhubungan dengan file
        
        Args:
            tipe_operasi: Jenis operasi (e.g., "Proses", "Unggah", "Unduh")
            file_path: Path ke file
            sukses: Apakah operasi berhasil (True/False)
            detail: Detail tambahan (opsional)
        """
        nama_file = Path(file_path).name
        
        if sukses:
            self.sukses(f"{tipe_operasi} file berhasil", f"{nama_file}")
        else:
            self.kesalahan(f"{tipe_operasi} file gagal", f"{nama_file}{' - ' + detail if detail else ''}")

# Buat instance default
logger = SotongLogger()

# Contoh penggunaan
if __name__ == "__main__":
    logger.info("Aplikasi dimulai")
    logger.sukses("Proses selesai", "5 file berhasil diproses")
    logger.peringatan("File terlalu besar", "image.jpg (10MB)")
    logger.kesalahan("Gagal menghubungi server")
    logger.debug("Variabel X = 10")
    
    # Log operasi file
    logger.log_operasi_file("Proses", "C:/gambar/foto.jpg", True)
    logger.log_operasi_file("Unduh", "C:/gambar/foto_hasil.png", False, "Koneksi terputus")
