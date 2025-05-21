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

class ImageProcessor:
    def __init__(self, chromedriver_path: str = None, progress_callback: Callable = None):
        """
        Inisialisasi prosesor gambar
        
        Args:
            chromedriver_path: Path ke chromedriver.exe
            progress_callback: Callback untuk melaporkan progres ke UI
        """
        self.chromedriver_path = chromedriver_path or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "driver", "chromedriver.exe")
        self.progress_callback = progress_callback
        self.should_stop = False
        self.processing_thread = None
        self.total_processed = 0
        self.total_failed = 0
        self.results = []
        self.start_time = None
        self.end_time = None
        self.polling_interval = 1  # cek setiap 1 detik (sesuai permintaan)
        
    def update_progress(self, message: str, percentage: int = None, current: int = None, total: int = None):
        """
        Update progres ke UI
        
        Args:
            message: Pesan untuk ditampilkan
            percentage: Persentase penyelesaian (0-100)
            current: Nomor file saat ini
            total: Total file yang diproses
        """
        if self.progress_callback:
            if current is not None and total is not None:
                message = f"{message} [{current}/{total}]"
                
            self.progress_callback(message, percentage)
    
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
            return
        
        # Mulai thread untuk pemrosesan
        self.processing_thread = threading.Thread(
            target=self._process_files,
            args=(files_to_process,)
        )
        self.processing_thread.daemon = True
        self.processing_thread.start()
    
    def stop_processing(self):
        """Menghentikan pemrosesan"""
        self.should_stop = True
        if self.processing_thread and self.processing_thread.is_alive():
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
                break
                
            current_num = i + 1
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
                else:
                    self.total_failed += 1
                    
            except Exception as e:
                self.total_failed += 1
                self.results.append({
                    "file_path": file_path,
                    "success": False,
                    "error": str(e)
                })
        
        self.end_time = datetime.now()
        self.update_progress(
            f"Selesai! Berhasil: {self.total_processed}, Gagal: {self.total_failed}",
            percentage=100
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
        result = {
            "file_path": file_path,
            "success": False,
            "enhanced_path": None,
            "error": None,
            "start_time": datetime.now()
        }
        
        try:
            # Konfigurasi browser untuk headless mode
            chrome_options = Options()
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--log-level=3")
            chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])

            # Inisialisasi Chrome dengan lokasi driver
            driver = webdriver.Chrome(service=Service(self.chromedriver_path), options=chrome_options)
            
            try:
                # Buka halaman Picsart AI Image Enhancer
                self.update_progress(f"Membuka browser untuk file {Path(file_path).name}", current=current_num, total=total_files)
                driver.get("https://picsart.com/id/ai-image-enhancer/")
                time.sleep(2)  # Tunggu halaman dan elemen render

                # Cari elemen input type="file" (biasanya disembunyikan oleh CSS)
                input_file = driver.find_element(By.XPATH, "//input[@type='file']")
                
                # Upload file ke elemen input
                input_file.send_keys(file_path)

                self.update_progress(f"File dikirim: {Path(file_path).name}", current=current_num, total=total_files)
                
                # Tunggu sampai element dengan data-testid="EnhancedImage" muncul
                self.update_progress(f"Menunggu proses enhancement: {Path(file_path).name}", current=current_num, total=total_files)
                
                # Implementasi retry logic dengan timeout keseluruhan
                max_wait_time = 300  # 5 menit total
                start_time = time.time()
                
                found_image = False
                image_url = None
                
                while time.time() - start_time < max_wait_time and not found_image and not self.should_stop:
                    try:
                        # Hitung persentase progress dari waktu pemrosesan
                        elapsed = time.time() - start_time
                        # Asumsikan proses enhancement membutuhkan sekitar 60 detik
                        process_percent = min(95, int(elapsed / 60 * 100))
                        overall_percent = int(((current_num - 1) / total_files * 100) + (process_percent / total_files))
                        
                        self.update_progress(
                            f"Memproses enhancement: {Path(file_path).name} ({int(elapsed)} detik)", 
                            percentage=overall_percent,
                            current=current_num, 
                            total=total_files
                        )
                        
                        # Coba beberapa selector berbeda untuk menemukan gambar yang dienhance
                        possible_selectors = [
                            'div[data-testid="EnhancedImage"] img',
                            'div.widget-widgetContainer-0-1-1014[data-testid="EnhancedImage"] img',
                            'img[alt*="enhanced"]',
                            'div[data-testid="EnhancedImage"] *[src]'
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
                    return result
                    
                if not found_image:
                    self.update_progress(f"Gagal memproses: {Path(file_path).name}", current=current_num, total=total_files)
                    result["error"] = "Tidak dapat menemukan gambar hasil enhancement dalam batas waktu"
                    # Ambil screenshot sebagai bukti
                    screenshot_path = os.path.join(os.path.dirname(file_path), "UPSCALE", f"error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
                    os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
                    driver.save_screenshot(screenshot_path)
                    return result
                
                self.update_progress(f"Gambar enhancement ditemukan: {Path(file_path).name}", current=current_num, total=total_files)
                
                # Download image
                response = requests.get(image_url, stream=True)
                if response.status_code == 200:
                    # Buat nama file dengan timestamp
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    file_name = Path(file_path).stem
                    
                    # Buat folder UPSCALE di lokasi file asli
                    output_folder = os.path.join(os.path.dirname(file_path), "UPSCALE")
                    os.makedirs(output_folder, exist_ok=True)
                    
                    # Simpan file
                    enhanced_path = os.path.join(output_folder, f"{file_name}_upscaled_{timestamp}.png")
                    with open(enhanced_path, 'wb') as f:
                        for chunk in response.iter_content(1024):
                            f.write(chunk)
                    
                    self.update_progress(f"Gambar berhasil diunduh: {Path(enhanced_path).name}", current=current_num, total=total_files)
                    result["success"] = True
                    result["enhanced_path"] = enhanced_path
                else:
                    self.update_progress(f"Gagal mengunduh gambar. Status code: {response.status_code}", current=current_num, total=total_files)
                    result["error"] = f"Gagal mengunduh gambar. Status code: {response.status_code}"
            finally:
                driver.quit()
                
        except Exception as e:
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