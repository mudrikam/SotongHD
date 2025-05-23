from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import time
import requests
import os
from datetime import datetime
import glob
from pathlib import Path
from typing import List, Dict, Tuple, Callable
import threading
import sys
from PySide6.QtCore import QObject, Signal
from .logger import logger

# Add a signal class for progress updates
class ProgressSignal(QObject):
    progress = Signal(str, int)  # Signal with message and percentage

# Add a signal class for file updates
class FileUpdateSignal(QObject):
    file_update = Signal(str, bool)  # Signal with file path and completion flag

class ImageProcessor:
    def __init__(self, chromedriver_path: str = None, progress_callback: Callable = None, 
                 progress_signal: ProgressSignal = None, file_update_signal: FileUpdateSignal = None):
        """
        Inisialisasi prosesor gambar
        
        Args:
            chromedriver_path: Path ke chromedriver.exe
            progress_callback: Callback untuk melaporkan progres ke UI (deprecated)
            progress_signal: Signal untuk melaporkan progres ke UI (recommended)
            file_update_signal: Signal untuk melaporkan file yang sedang diproses
        """
        self.chromedriver_path = chromedriver_path or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "driver", "chromedriver.exe")
        self.progress_callback = progress_callback  # Keep for backward compatibility
        self.progress_signal = progress_signal      # New signal-based approach
        self.file_update_signal = file_update_signal  # Signal for file updates
        self.should_stop = False
        self.processing_thread = None
        self.total_processed = 0
        self.total_failed = 0
        self.results = []
        self.start_time = None
        self.end_time = None
        self.polling_interval = 1  # cek setiap 1 detik (sesuai permintaan)
        
        logger.info("SotongHD Image Processor diinisialisasi")
        
    def update_progress(self, message: str, percentage: int = None, current: int = None, total: int = None):
        """
        Update progres ke UI
        
        Args:
            message: Pesan untuk ditampilkan
            percentage: Persentase penyelesaian (0-100)
            current: Nomor file saat ini
            total: Total file yang diproses
        """
        if current is not None and total is not None:
            message = f"{message} [{current}/{total}]"
        
        # Use signal if available (preferred), otherwise fall back to callback
        if self.progress_signal:
            self.progress_signal.progress.emit(message, percentage if percentage is not None else 0)
        elif self.progress_callback:
            self.progress_callback(message, percentage)
        
        # Only log significant progress updates (starting, completion, and milestones)
        is_milestone = percentage is not None and (percentage == 0 or percentage == 100 or percentage % 25 == 0)
        is_important_message = "berhasil" in message.lower() or "gagal" in message.lower() or "error" in message.lower()
        
        if is_milestone or is_important_message:
            logger.info(message, f"{percentage}%" if percentage is not None else None)
    
    def get_files_to_process(self, paths: List[str]) -> List[str]:
        """
        Mendapatkan daftar file yang akan diproses
        
        Args:
            paths: Daftar path file atau folder
            
        Returns:
            List[str]: Daftar path file yang akan diproses
        """
        all_files = []
        
        for path in paths:
            path_obj = Path(path)
            
            if path_obj.is_file() and self._is_image_file(path):
                all_files.append(str(path_obj))
            elif path_obj.is_dir():
                # Cari semua file gambar dalam folder dan subfoldernya
                for ext in ['*.jpg', '*.jpeg', '*.png', '*.bmp', '*.gif']:
                    all_files.extend(glob.glob(os.path.join(path, '**', ext), recursive=True))
        
        return all_files
    
    def _is_image_file(self, file_path: str) -> bool:
        """
        Memeriksa apakah file adalah gambar
        
        Args:
            file_path: Path ke file
            
        Returns:
            bool: True jika file adalah gambar, False jika bukan
        """
        valid_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.gif']
        return Path(file_path).suffix.lower() in valid_extensions
    
    def start_processing(self, paths: List[str]):
        """
        Memulai pemrosesan gambar dalam thread terpisah
        
        Args:
            paths: Daftar path file atau folder
        """
        self.should_stop = False
        self.total_processed = 0
        self.total_failed = 0
        self.results = []
        self.start_time = datetime.now()
        
        # Mendapatkan daftar file yang akan diproses
        files_to_process = self.get_files_to_process(paths)
        
        if not files_to_process:
            self.update_progress("Tidak ada file gambar ditemukan", 100)
            logger.warning("Tidak ada file gambar ditemukan", f"Paths: {', '.join(paths)}")
            return
        
        logger.info(f"Mulai memproses {len(files_to_process)} file gambar")
        
        # Mulai thread untuk pemrosesan
        self.processing_thread = threading.Thread(
            target=self._process_files,
            args=(files_to_process,)
        )
        self.processing_thread.daemon = True
        self.processing_thread.start()
    
    def stop_processing(self):
        """Menghentikan pemrosesan"""
        if self.processing_thread and self.processing_thread.is_alive():
            logger.info("Menghentikan pemrosesan berdasarkan permintaan pengguna")
            self.should_stop = True
            self.processing_thread.join(10)  # Tunggu maksimal 10 detik
    
    def _process_files(self, files: List[str]):
        """
        Proses semua file dalam daftar
        
        Args:
            files: Daftar path file yang akan diproses
        """
        total_files = len(files)
        
        for i, file_path in enumerate(files):
            if self.should_stop:
                logger.info("Pemrosesan dihentikan")
                break
                
            current_num = i + 1
            file_name = Path(file_path).name
            
            # Only log the start of processing for each file, not detailed steps
            if current_num == 1 or current_num == total_files or current_num % 5 == 0:
                logger.info(f"Memproses file {current_num} dari {total_files}", f"{file_name}")
            
            # Signal that we're processing a new file
            if self.file_update_signal:
                self.file_update_signal.file_update.emit(file_path, False)
                
            self.update_progress(
                f"Memproses file", 
                percentage=int((i / total_files) * 100),
                current=current_num,
                total=total_files
            )
            
            try:
                result = self.process_image(file_path, current_num, total_files)
                self.results.append(result)
                
                if result["success"]:
                    self.total_processed += 1
                    logger.sukses("Berhasil memproses gambar", file_name)
                else:
                    self.total_failed += 1
                    logger.kesalahan("Gagal memproses gambar", f"{file_name} - {result.get('error', 'Alasan tidak diketahui')}")
                    
            except Exception as e:
                self.total_failed += 1
                logger.kesalahan("Error saat memproses gambar", f"{file_name} - {str(e)}")
        
        self.end_time = datetime.now()
        
        # Signal processing completion for UI update
        if self.file_update_signal:
            self.file_update_signal.file_update.emit("", True)
            
        self.update_progress(
            f"Selesai! Berhasil: {self.total_processed}, Gagal: {self.total_failed}",
            percentage=100
        )
        
        logger.sukses(
            f"Selesai memproses semua gambar. Berhasil: {self.total_processed}, Gagal: {self.total_failed}",
            f"Durasi: {(self.end_time - self.start_time).total_seconds():.1f} detik"
        )
    
    def process_image(self, file_path: str, current_num: int, total_files: int) -> Dict:
        """
        Proses satu file gambar
        
        Args:
            file_path: Path ke file gambar
            current_num: Nomor file saat ini
            total_files: Total file yang diproses
            
        Returns:
            Dict: Hasil pemrosesan dalam bentuk dictionary
        """
        file_name = Path(file_path).name
        
        result = {
            "file_path": file_path,
            "success": False,
            "enhanced_path": None,
            "error": None,
            "start_time": datetime.now()
        }
        
        # Definisi distribusi persentase setiap tahap proses
        # Total harus 100%
        percentages = {
            "browser_setup": 5,     # 0-5%: Setup browser
            "upload": 10,           # 5-15%: Upload gambar
            "processing": 65,       # 15-80%: Menunggu proses enhancement
            "downloading": 15,      # 80-95%: Download hasil
            "saving": 5             # 95-100%: Menyimpan & finalisasi
        }
        
        # Offset persentase untuk file saat ini dalam keseluruhan proses
        # Misal: jika ada 4 file, file ke-2 akan mulai dari 25% dan berakhir di 50%
        file_percent_size = 100 / total_files
        file_start_percent = (current_num - 1) * file_percent_size
        
        # Function untuk menghitung persentase global
        def calculate_global_percent(stage_percent):
            # Konversi persentase tahap (0-100) ke persentase global (sesuai posisi file)
            local_percent = stage_percent / 100 * file_percent_size
            return int(file_start_percent + local_percent)
        
        try:
            # ===== TAHAP 1: Setup Browser (0-5%) =====
            # Don't log routine browser setup steps
            self.update_progress(
                f"Mempersiapkan chrome untuk file {Path(file_path).name}", 
                percentage=calculate_global_percent(percentages["browser_setup"] / 2),
                current=current_num, 
                total=total_files
            )
            
            # Konfigurasi browser untuk headless mode
            chrome_options = Options()
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1366,768")
            chrome_options.add_argument("--log-level=3")
            chrome_options.add_argument("--incognito")  # Add incognito mode
            chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])

            # Inisialisasi Chrome dengan lokasi driver
            driver = webdriver.Chrome(service=Service(self.chromedriver_path), options=chrome_options)
            
            try:
                # Buka halaman Picsart AI Image Enhancer
                self.update_progress(
                    f"Membuka situs untuk file {Path(file_path).name}", 
                    percentage=calculate_global_percent(percentages["browser_setup"]),
                    current=current_num, 
                    total=total_files
                )
                
                driver.get("https://picsart.com/id/ai-image-enhancer/")
                time.sleep(2)  # Tunggu halaman dan elemen render

                # ===== TAHAP 2: Upload Gambar (5-15%) =====
                # Only log key events, not routine steps
                self.update_progress(
                    f"Mengunggah gambar: {Path(file_path).name}", 
                    percentage=calculate_global_percent(percentages["browser_setup"] + percentages["upload"] / 2),
                    current=current_num, 
                    total=total_files
                )
                
                # Perbaikan metode pencarian elemen input file
                # Gunakan multiple selectors untuk meningkatkan reliabilitas
                input_file = None
                selectors_to_try = [
                    "div[id='uploadArea'] input[type='file']",
                    "div[id='uploadArea'] input",
                    "div[class*='upload-area-root'] input[type='file']",
                    "div[class*='upload-area'] input[type='file']",
                    "div[class*='upload-area'] input",
                    "input[data-testid='input']",
                    "input[accept*='image/jpeg']"
                ]
                
                for selector in selectors_to_try:
                    try:
                        input_file = driver.find_element(By.CSS_SELECTOR, selector)
                        if input_file:
                            logger.info(f"Mencoba mengunggah gambar ke: {selector}")
                            break
                    except:
                        continue
                
                if not input_file:
                    # Jika masih tidak ditemukan, coba menggunakan JavaScript untuk menemukan elemen
                    logger.info("Mencoba mencari elemen dengan JavaScript")
                    try:
                        input_file = driver.execute_script("""
                            return document.querySelector("div[id='uploadArea'] input") || 
                                   document.querySelector("input[type='file']") ||
                                   document.querySelector("input[data-testid='input']");
                        """)
                    except:
                        pass
                
                if not input_file:
                    # Ambil screenshot untuk debugging
                    debug_screenshot_path = os.path.join(os.path.dirname(file_path), "UPSCALE", "debug_screenshot.png")
                    os.makedirs(os.path.dirname(debug_screenshot_path), exist_ok=True)
                    driver.save_screenshot(debug_screenshot_path)
                    
                    # Log page source untuk analisis
                    html_source = driver.page_source
                    debug_html_path = os.path.join(os.path.dirname(file_path), "UPSCALE", "page_source.html")
                    with open(debug_html_path, 'w', encoding='utf-8') as f:
                        f.write(html_source)
                    
                    raise Exception("Tidak dapat menemukan elemen input file. Screenshot dan HTML source disimpan untuk debugging.")

                # Upload file ke elemen input
                input_file.send_keys(file_path)
                time.sleep(2)  # Beri waktu lebih lama untuk upload selesai (ditambah dari 1 detik)

                self.update_progress(
                    f"File berhasil diunggah: {Path(file_path).name}", 
                    percentage=calculate_global_percent(percentages["browser_setup"] + percentages["upload"]),
                    current=current_num, 
                    total=total_files
                )
                
                # ===== TAHAP 3: Menunggu Proses Enhancement (15-80%) =====
                # Only log the start of waiting, not every interval
                self.update_progress(
                    f"Menunggu proses enhancement: {Path(file_path).name}", 
                    percentage=calculate_global_percent(percentages["browser_setup"] + percentages["upload"] + 5),
                    current=current_num, 
                    total=total_files
                )
                
                # Implementasi retry logic dengan timeout keseluruhan
                max_wait_time = 300  # 5 menit total
                start_time = time.time()
                
                found_image = False
                image_url = None
                
                # Menunggu gambar muncul
                processing_percent_range = percentages["processing"] - 5  # Dikurangi 5 yang sudah digunakan di atas
                
                while time.time() - start_time < max_wait_time and not found_image and not self.should_stop:
                    try:
                        # Hitung persentase progress berdasarkan waktu yang telah berlalu
                        elapsed = time.time() - start_time
                        elapsed_percent = min(100, int(elapsed / 60 * 100))  # 60 detik = 100%
                        
                        # Konversi ke persentase dalam range tahap pemrosesan
                        process_stage_percent = (elapsed_percent / 100) * processing_percent_range
                        
                        # Update progress dengan persentase global
                        stage_percent = percentages["browser_setup"] + percentages["upload"] + 5 + process_stage_percent
                        
                        self.update_progress(
                            f"Memproses enhancement: {Path(file_path).name} ({int(elapsed)} detik)", 
                            percentage=calculate_global_percent(stage_percent),
                            current=current_num, 
                            total=total_files
                        )
                        
                        # Coba beberapa selector berbeda untuk menemukan gambar yang dienhance
                        possible_selectors = [
                            'div[data-testid="EnhancedImage"] img',
                            'div[data-testid="EnhancedImage"][class*="widget-widgetContainer"] img',
                            'div[data-testid="EnhancedImage"] *[src]',
                            'img[alt*="enhanced"]',
                            'div[data-testid="EnhancedImage"]>div>img',
                            'div[data-testid="EnhancedImage"] picture img'
                        ]
                        
                        for selector in possible_selectors:
                            try:
                                # Gunakan script JavaScript untuk cek visibilitas elemen
                                img_elements = driver.execute_script(f"""
                                    return document.querySelectorAll('{selector}');
                                """)
                                
                                if len(img_elements) > 0:
                                    for img in img_elements:
                                        image_url = img.get_attribute("src")
                                        if image_url and "http" in image_url:
                                            found_image = True
                                            break
                                    
                                    if found_image:
                                        break
                            except Exception as e:
                                continue
                        
                        if not found_image:
                            time.sleep(self.polling_interval)
                    except Exception:
                        time.sleep(self.polling_interval)
                
                if self.should_stop:
                    result["error"] = "Proses dihentikan pengguna"
                    logger.info("Pemrosesan dibatalkan oleh pengguna", file_name)
                    return result
                    
                if not found_image:
                    self.update_progress(
                        f"Gagal memproses: {Path(file_path).name}", 
                        percentage=calculate_global_percent(percentages["browser_setup"] + percentages["upload"] + percentages["processing"]),
                        current=current_num, 
                        total=total_files
                    )
                    
                    logger.kesalahan("Timeout menunggu hasil enhancement", file_name)
                    # Ambil screenshot sebagai bukti
                    screenshot_path = os.path.join(os.path.dirname(file_path), "UPSCALE", f"error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
                    os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
                    driver.save_screenshot(screenshot_path)
                    return result
                
                # ===== TAHAP 4: Download Gambar (80-95%) =====
                # Log important milestone - image found
                logger.info(f"Menemukan gambar hasil", file_name)
                
                # Download image
                response = requests.get(image_url, stream=True)
                
                if response.status_code == 200:
                    # Persiapan download
                    self.update_progress(
                        f"Mengunduh gambar enhancement: {Path(file_path).name}", 
                        percentage=calculate_global_percent(percentages["browser_setup"] + percentages["upload"] + percentages["processing"] + percentages["downloading"] / 2),
                        current=current_num, 
                        total=total_files
                    )
                    
                    # ===== TAHAP 5: Menyimpan Gambar (95-100%) =====
                    # Buat nama file dengan timestamp
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    file_name = Path(file_path).stem
                    
                    # Buat folder UPSCALE di lokasi file asli
                    output_folder = os.path.join(os.path.dirname(file_path), "UPSCALE")
                    os.makedirs(output_folder, exist_ok=True)
                    
                    # Simpan file
                    enhanced_path = os.path.join(output_folder, f"{file_name}_upscaled_{timestamp}.png")
                    
                    enhanced_file_name = Path(enhanced_path).name
                    # Log saving - important step
                    logger.info(f"Menyimpan hasil enhancement", enhanced_file_name)
                    self.update_progress(
                        f"Menyimpan gambar: {Path(enhanced_path).name}", 
                        percentage=calculate_global_percent(100 - percentages["saving"]),
                        current=current_num, 
                        total=total_files
                    )
                    
                    with open(enhanced_path, 'wb') as f:
                        for chunk in response.iter_content(1024):
                            f.write(chunk)
                    
                    # Proses selesai untuk file ini
                    self.update_progress(
                        f"Gambar berhasil disimpan: {Path(enhanced_path).name}", 
                        percentage=calculate_global_percent(100),
                        current=current_num, 
                        total=total_files
                    )
                    
                    # Log success - critical information
                    logger.sukses(f"Berhasil menyimpan gambar enhancement", enhanced_file_name)
                    
                    result["success"] = True
                    result["enhanced_path"] = enhanced_path
                else:
                    self.update_progress(
                        f"Gagal mengunduh gambar. Status code: {response.status_code}", 
                        percentage=calculate_global_percent(percentages["browser_setup"] + percentages["upload"] + percentages["processing"] + percentages["downloading"]),
                        current=current_num, 
                        total=total_files
                    )
                    
                    # Log failure - critical information
                    logger.kesalahan(f"Gagal mengunduh hasil. Status code: {response.status_code}", file_name)
                    result["error"] = f"Gagal mengunduh gambar. Status code: {response.status_code}"
            finally:
                driver.quit()
                
        except Exception as e:
            # Always log errors - critical information
            logger.kesalahan(f"Error saat memproses gambar", f"{file_name} - {str(e)}")
            result["error"] = str(e)
            
        result["end_time"] = datetime.now()
        result["duration"] = (result["end_time"] - result["start_time"]).total_seconds()
        return result
        
    def get_statistics(self) -> Dict:
        """
        Mendapatkan statistik hasil pemrosesan
        
        Returns:
            Dict: Statistik pemrosesan
        """
        if self.start_time and self.end_time:
            duration = (self.end_time - self.start_time).total_seconds()
        else:
            duration = 0
            
        stats = {
            "total_processed": self.total_processed,
            "total_failed": self.total_failed,
            "total_duration": duration,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "results": self.results,
            "processed_folders": set(),
        }
        
        # Tambahkan informasi folder yang diproses
        for result in self.results:
            if "file_path" in result:
                folder = os.path.dirname(result["file_path"])
                stats["processed_folders"].add(folder)
                
        stats["processed_folders"] = list(stats["processed_folders"])
        return stats