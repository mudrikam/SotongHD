import os
import sys
import logging
import re
from datetime import datetime
from pathlib import Path
from PySide6.QtWidgets import QTextEdit
from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtGui import QTextCursor

class LogUISignal(QObject):
    log_message = Signal(str, str)

class SotongLogger:
    INFO = 0
    SUKSES = 1
    PERINGATAN = 2
    KESALAHAN = 3
    DEBUG = 4
    
    WARNA = {
        'reset': '\033[0m',
        'hijau': '\033[92m',
        'kuning': '\033[93m',
        'merah': '\033[91m',
        'biru': '\033[94m',
        'ungu': '\033[95m'
    }
    
    HTML_WARNA = {
        'info': "#3498db",
        'sukses': "#2ecc71",
        'peringatan': "#f39c12",
        'kesalahan': "#e74c3c",
        'debug': "#9b59b6"
    }
    
    def __init__(self, log_folder=None, console_output=True, file_output=True, level=0):
        self.console_output = console_output
        self.file_output = file_output
        self.level = level
        self.log_ui_signal = LogUISignal()
        self.ui_initialized = False
        self.log_widget = None
        
        self.warna_didukung = sys.stdout.isatty()
        
        if file_output:
            if log_folder is None:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                log_folder = os.path.join(base_dir, "Logs")
            
            os.makedirs(log_folder, exist_ok=True)
            
            tanggal_sekarang = datetime.now().strftime("%Y-%m-%d")
            self.log_file = os.path.join(log_folder, f"sotonghd_{tanggal_sekarang}.log")
    
    def set_log_widget(self, widget: QTextEdit):
        self.log_widget = widget
        self.ui_initialized = True
        self.log_ui_signal.log_message.connect(self._update_log_widget)
        widget.document().setMaximumBlockCount(500)
    
    def _update_log_widget(self, message: str, level: str):
        if not self.log_widget:
            return
            
        color = self.HTML_WARNA.get(level.lower(), "#000000")
        html_message = f'<span style="color:{color};">{message}</span><br>'
        self.log_widget.insertHtml(html_message)
        cursor = self.log_widget.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_widget.setTextCursor(cursor)
        self.log_widget.ensureCursorVisible()
    
    def _translate_message(self, msg: str) -> str:
        # simple deterministic term mapping to produce technical Indonesian messages
        replacements = [
            (r"\bfail(?:ed)?\b", "gagal"),
            (r"\bnot found\b", "tidak ditemukan"),
            (r"\bno files found\b", "tidak ada file ditemukan"),
            (r"\bmissing\b", "hilang"),
            (r"\bskip(?:ping)?\b", "melewatkan"),
            (r"\bstart(?:ing)?\b", "memulai"),
            (r"\bcomplete(?:d)?\b", "selesai"),
            (r"\bmerge\b", "gabung"),
            (r"\berror\b", "kesalahan"),
            (r"\bpermission\b", "izin"),
            (r"\bexecutable\b", "eksekusi"),
            (r"\bdriver\b", "driver"),
            (r"\btimeout\b", "batas waktu"),
            (r"\bprogress\b", "progres"),
        ]
        out = msg
        for pat, repl in replacements:
            out = re.sub(pat, repl, out, flags=re.IGNORECASE)
        return out

    def _log(self, level, pesan, detail=None):
        if level < self.level:
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
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
            
        # translate pesan to Indonesian technical phrasing deterministically
        try:
            pesan = self._translate_message(str(pesan))
        except Exception:
            pesan = str(pesan)

        log_message = f"[{timestamp}] {level_text}: {pesan}"
        if detail:
            log_message += f" - {detail}"
        if self.console_output:
            if self.warna_didukung:
                print(f"{warna}{log_message}{self.WARNA['reset']}")
            else:
                print(log_message)
        if self.file_output:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_message + "\n")
        if self.ui_initialized:
            self.log_ui_signal.log_message.emit(log_message, level_name)
    
    def info(self, pesan, detail=None):
        self._log(self.INFO, pesan, detail)
    
    def sukses(self, pesan, detail=None):
        self._log(self.SUKSES, pesan, detail)
        
    def peringatan(self, pesan, detail=None):
        self._log(self.PERINGATAN, pesan, detail)
        
    def kesalahan(self, pesan, detail=None):
        self._log(self.KESALAHAN, pesan, detail)
        
    def debug(self, pesan, detail=None):
        self._log(self.DEBUG, pesan, detail)
    
    def log_operasi_file(self, tipe_operasi, file_path, sukses=True, detail=None):
        nama_file = Path(file_path).name
        
        if sukses:
            self.sukses(f"{tipe_operasi} file berhasil", f"{nama_file}")
        else:
            self.kesalahan(f"{tipe_operasi} file gagal", f"{nama_file}{' - ' + detail if detail else ''}")

logger = SotongLogger()

if __name__ == "__main__":
    logger.info("Aplikasi dimulai")
    logger.sukses("Proses selesai", "5 file berhasil diproses")
    logger.peringatan("File terlalu besar", "image.jpg (10MB)")
    logger.kesalahan("Gagal menghubungi server")
    logger.debug("Variabel X = 10")
    
    logger.log_operasi_file("Proses", "C:/gambar/foto.jpg", True)
    logger.log_operasi_file("Unduh", "C:/gambar/foto_hasil.png", False, "Koneksi terputus")
