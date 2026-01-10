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
                 progress_signal: ProgressSignal = None, file_update_signal: FileUpdateSignal = None,
                 config_manager=None, headless: bool | None = None, incognito: bool | None = None):
        """
        Inisialisasi prosesor gambar
        
        Args:
            chromedriver_path: Path ke chromedriver.exe
            progress_callback: Callback untuk melaporkan progres ke UI (deprecated)
            progress_signal: Signal untuk melaporkan progres ke UI (recommended)
            file_update_signal: Signal untuk melaporkan file yang sedang diproses
            config_manager: Manager for configuration settings
        """
        # Cross-platform chromedriver path
        driver_filename = 'chromedriver.exe' if sys.platform == 'win32' else 'chromedriver'
        self.chromedriver_path = chromedriver_path or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "driver", driver_filename)
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
        self.config_manager = config_manager
        # Browser options provided by UI; None means 'unspecified' (don't assume)
        self.headless = headless
        self.incognito = incognito
        # Batch processing: number of concurrent browser instances/tabs to use
        # Default 1 (sequential). GUI will set this prior to start_processing.
        self.batch_size = 1
        
        
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

        # Respect configured batch size (minimum 1, maximum reasonable cap 10)
        batch_size = max(1, int(getattr(self, 'batch_size', 1) or 1))
        if batch_size > 20:
            # Safety cap to avoid massive parallelism
            batch_size = 20

        logger.info(f"Memproses {total_files} file dengan batch_size={batch_size}")

        # Process files in chunks of batch_size
        for start in range(0, total_files, batch_size):
            if self.should_stop:
                logger.info("Pemrosesan dihentikan")
                break

            chunk = files[start:start + batch_size]
            drivers = [None] * len(chunk)
            chunk_results = [None] * len(chunk)

            # Launch one browser instance per item in the chunk
            for idx, file_path in enumerate(chunk):
                if self.should_stop:
                    break

                current_num = start + idx + 1
                file_name = Path(file_path).name

                # Signal that we're processing a new file
                if self.file_update_signal:
                    self.file_update_signal.file_update.emit(file_path, False)

                # Update progress (start of browser setup for this file)
                self.update_progress(
                    f"Memproses file",
                    percentage=int(( (start + idx) / total_files) * 100),
                    current=current_num,
                    total=total_files
                )

                try:
                    # Setup browser for this slot
                    try:
                        chrome_options = Options()
                        if self.headless is True:
                            try:
                                chrome_options.add_argument("--headless=new")
                            except Exception:
                                chrome_options.add_argument("--headless")

                        chrome_options.add_argument("--disable-gpu")
                        chrome_options.add_argument("--window-size=1366,768")
                        chrome_options.add_argument("--log-level=3")
                        if self.incognito:
                            chrome_options.add_argument("--incognito")
                        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])

                        # Build capabilities and apply defensive filtering similar to single-run logic
                        try:
                            caps = chrome_options.to_capabilities() or {}
                        except Exception:
                            caps = {}

                        current_args = caps.get('goog:chromeOptions', {}).get('args', []) or []
                        filtered_args = []
                        for a in current_args:
                            if self.headless is False and (a.startswith('--headless') or a == '--headless'):
                                continue
                            if self.incognito is False and a == '--incognito':
                                continue
                            filtered_args.append(a)

                        base_required = ['--disable-gpu', '--window-size=1366,768', '--log-level=3']
                        for req in base_required:
                            if req not in filtered_args:
                                filtered_args.append(req)

                        if self.incognito is True and '--incognito' not in filtered_args:
                            filtered_args.append('--incognito')

                        if self.headless is True and not any(x.startswith('--headless') for x in filtered_args):
                            try:
                                filtered_args.insert(0, '--headless=new')
                            except Exception:
                                filtered_args.insert(0, '--headless')

                        caps.setdefault('goog:chromeOptions', {})['args'] = filtered_args

                        logger.info(f"Launching Chrome slot={idx} - headless={self.headless}, incognito={self.incognito}", str(caps.get('goog:chromeOptions', caps)))

                        try:
                            driver = webdriver.Chrome(service=Service(self.chromedriver_path), desired_capabilities=caps)
                        except TypeError:
                            driver = webdriver.Chrome(service=Service(self.chromedriver_path), options=chrome_options)

                        drivers[idx] = driver
                        # Open the target page but do not upload yet
                        driver.get("https://picsart.com/id/ai-image-enhancer/")

                    except Exception as e:
                        logger.kesalahan("Gagal membuka browser untuk file", f"{file_name} - {str(e)}")
                        chunk_results[idx] = {
                            "file_path": file_path,
                            "success": False,
                            "enhanced_path": None,
                            "error": str(e),
                            "start_time": datetime.now(),
                            "end_time": datetime.now(),
                            "duration": 0
                        }
                        # Ensure driver slot remains None
                        drivers[idx] = None
                except Exception as e:
                    logger.kesalahan("Unexpected error during browser setup", str(e))

            # Wait until all non-None drivers have the upload element ready
            upload_selectors = [
                "div[id='uploadArea'] input[type='file']",
                "div[id='uploadArea'] input",
                "div[class*='upload-area-root'] input[type='file']",
                "div[class*='upload-area'] input[type='file']",
                "div[class*='upload-area'] input",
                "input[data-testid='input']",
                "input[accept*='image/jpeg']"
            ]

            all_ready = False
            while not all_ready and not self.should_stop:
                all_ready = True
                for d in drivers:
                    if d is None:
                        continue
                    try:
                        ready = None
                        try:
                            ready = d.execute_script("return document.readyState")
                        except Exception:
                            ready = None

                        found = False
                        for sel in upload_selectors:
                            try:
                                elems = d.find_elements(By.CSS_SELECTOR, sel)
                                if elems and len(elems) > 0:
                                    found = True
                                    break
                            except Exception:
                                continue

                        if not (ready == 'complete' and found):
                            all_ready = False
                            break
                    except Exception:
                        all_ready = False
                        break

                if not all_ready:
                    time.sleep(self.polling_interval)

            if self.should_stop:
                # Clean up any open drivers
                for d in drivers:
                    try:
                        if d:
                            d.quit()
                    except Exception:
                        pass
                break

            # Now upload files into each ready driver
            for idx, d in enumerate(drivers):
                if d is None:
                    continue

                file_path = chunk[idx]
                file_name = Path(file_path).name

                # Find input element for this driver
                input_file = None
                for selector in upload_selectors:
                    try:
                        input_file = d.find_element(By.CSS_SELECTOR, selector)
                        if input_file:
                            logger.info(f"Slot {idx}: Mengunggah {file_name} ke selector {selector}")
                            break
                    except Exception:
                        continue

                if not input_file:
                    try:
                        input_file = d.execute_script("return document.querySelector('div[id=\'uploadArea\'] input') || document.querySelector('input[type=\'file\']') || document.querySelector('input[data-testid=\'input\']');")
                    except Exception:
                        input_file = None

                if not input_file:
                    # mark failure for this slot
                    logger.kesalahan("Slot upload element not found", file_name)
                    chunk_results[idx] = {
                        "file_path": file_path,
                        "success": False,
                        "enhanced_path": None,
                        "error": "Tidak dapat menemukan elemen input file",
                        "start_time": datetime.now(),
                        "end_time": datetime.now(),
                        "duration": 0
                    }
                    try:
                        d.quit()
                    except Exception:
                        pass
                    drivers[idx] = None
                    continue

                # send file path to input
                try:
                    input_file.send_keys(file_path)
                except Exception as e:
                    # If send_keys fails, mark this slot as failed and close the driver to avoid hanging
                    logger.kesalahan("Gagal mengirim file ke input upload", f"{file_name} - {str(e)}")
                    chunk_results[idx] = {
                        "file_path": file_path,
                        "success": False,
                        "enhanced_path": None,
                        "error": "Gagal mengirim file ke elemen input",
                        "start_time": datetime.now(),
                        "end_time": datetime.now(),
                        "duration": 0
                    }
                    try:
                        d.quit()
                    except Exception:
                        pass
                    drivers[idx] = None
                    continue

                # small pause to allow upload to start
                time.sleep(self.polling_interval)

            # After uploading, poll each driver for its EnhancedImage; close as each completes
            pending = sum(1 for r in drivers if r is not None)
            start_times = [datetime.now() for _ in chunk]

            while pending > 0 and not self.should_stop:
                for idx, d in enumerate(drivers):
                    if d is None:
                        continue

                    file_path = chunk[idx]
                    file_name = Path(file_path).name

                    # If this slot already has a result, skip
                    if chunk_results[idx] is not None:
                        continue

                    try:
                        # Check for enhanced image via JS selectors
                        possible_selectors = [
                            'div[data-testid="EnhancedImage"] img',
                            'div[data-testid="EnhancedImage"][class*="widget-widgetContainer"] img',
                            'div[data-testid="EnhancedImage"] *[src]',
                            'img[alt*="enhanced"]',
                            'div[data-testid="EnhancedImage"]>div>img',
                            'div[data-testid="EnhancedImage"] picture img'
                        ]

                        found_image = False
                        image_url = None
                        for selector in possible_selectors:
                            try:
                                img_elements = d.execute_script(f"return document.querySelectorAll('{selector}');")
                                if img_elements and len(img_elements) > 0:
                                    for img in img_elements:
                                        # img may be a remote element proxy; attempt to read src attr
                                        try:
                                            src = img.get_attribute('src')
                                        except Exception:
                                            try:
                                                src = d.execute_script('return arguments[0].getAttribute("src");', img)
                                            except Exception:
                                                src = None

                                        if src and 'http' in src:
                                            image_url = src
                                            found_image = True
                                            break
                                    if found_image:
                                        break
                            except Exception:
                                continue

                        if found_image and image_url:
                            # Download image (reuse single-file logic)
                            response = requests.get(image_url, stream=True)
                            if response.status_code == 200:
                                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                base_name = Path(file_path).stem
                                output_folder = os.path.join(os.path.dirname(file_path), "UPSCALE")
                                os.makedirs(output_folder, exist_ok=True)

                                output_format = "png"
                                if self.config_manager:
                                    output_format = self.config_manager.get_output_format()

                                enhanced_path = os.path.join(output_folder, f"{base_name}_{timestamp}.{output_format}")

                                if output_format == "jpg":
                                    try:
                                        from PIL import Image
                                        import io
                                        HAS_PIL = True
                                    except ImportError:
                                        HAS_PIL = False
                                        enhanced_path = os.path.join(output_folder, f"{base_name}_{timestamp}.png")
                                        with open(enhanced_path, 'wb') as f:
                                            for chunk_data in response.iter_content(1024):
                                                f.write(chunk_data)

                                    if HAS_PIL:
                                        temp_path = os.path.join(output_folder, f"{base_name}_temp_{timestamp}.png")
                                        with open(temp_path, 'wb') as f:
                                            for chunk_data in response.iter_content(1024):
                                                f.write(chunk_data)

                                        img = Image.open(temp_path)
                                        rgb_img = img.convert('RGB')
                                        rgb_img.save(enhanced_path, quality=95)
                                        if os.path.exists(temp_path):
                                            os.remove(temp_path)
                                else:
                                    with open(enhanced_path, 'wb') as f:
                                        for chunk_data in response.iter_content(1024):
                                            f.write(chunk_data)

                                # Mark success for this slot
                                chunk_results[idx] = {
                                    "file_path": file_path,
                                    "success": True,
                                    "enhanced_path": enhanced_path,
                                    "error": None,
                                    "start_time": start_times[idx],
                                    "end_time": datetime.now(),
                                    "duration": (datetime.now() - start_times[idx]).total_seconds()
                                }

                                logger.sukses(f"Berhasil menyimpan gambar enhancement", enhanced_path)

                                # Update progress for this file
                                current_num = start + idx + 1
                                self.update_progress(
                                    f"Gambar berhasil disimpan: {Path(enhanced_path).name}",
                                    percentage=int(((current_num) / total_files) * 100),
                                    current=current_num,
                                    total=total_files
                                )

                                # Close this driver
                                try:
                                    d.quit()
                                except Exception:
                                    pass
                                drivers[idx] = None
                                pending -= 1
                            else:
                                # download failed
                                chunk_results[idx] = {
                                    "file_path": file_path,
                                    "success": False,
                                    "enhanced_path": None,
                                    "error": f"Gagal mengunduh hasil. Status code: {response.status_code}",
                                    "start_time": start_times[idx],
                                    "end_time": datetime.now(),
                                    "duration": (datetime.now() - start_times[idx]).total_seconds()
                                }
                                logger.kesalahan(f"Gagal mengunduh hasil. Status code: {response.status_code}", file_name)
                                try:
                                    d.quit()
                                except Exception:
                                    pass
                                drivers[idx] = None
                                pending -= 1

                        else:
                            # Not ready yet; continue polling
                            continue

                    except Exception as e:
                        # Mark failure for this slot and ensure driver closed
                        logger.kesalahan("Error saat menunggu hasil di slot", f"{file_name} - {str(e)}")
                        chunk_results[idx] = {
                            "file_path": file_path,
                            "success": False,
                            "enhanced_path": None,
                            "error": str(e),
                            "start_time": start_times[idx],
                            "end_time": datetime.now(),
                            "duration": (datetime.now() - start_times[idx]).total_seconds()
                        }
                        try:
                            d.quit()
                        except Exception:
                            pass
                        drivers[idx] = None
                        pending -= 1

                # Sleep between polling cycles
                if pending > 0:
                    time.sleep(self.polling_interval)

            # At this point, chunk_results contains results for this batch (some may be None if driver setup failed earlier)
            # Normalize and append to global results, update counters
            for idx, file_path in enumerate(chunk):
                res = chunk_results[idx]
                if res is None:
                    # If still None, it means something unexpected; mark as failed
                    res = {
                        "file_path": file_path,
                        "success": False,
                        "enhanced_path": None,
                        "error": "Unknown error or aborted",
                        "start_time": datetime.now(),
                        "end_time": datetime.now(),
                        "duration": 0
                    }

                self.results.append(res)
                if res.get("success"):
                    self.total_processed += 1
                else:
                    self.total_failed += 1
        
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
            
            # Konfigurasi browser berdasarkan opsi UI (headless, incognito)
            chrome_options = Options()
            # Headless: support both boolean and new headless flag
            # Only enable headless if explicitly requested (True). If None, don't modify.
            if self.headless is True:
                try:
                    chrome_options.add_argument("--headless=new")
                except Exception:
                    chrome_options.add_argument("--headless")

            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1366,768")
            chrome_options.add_argument("--log-level=3")
            if self.incognito:
                chrome_options.add_argument("--incognito")
            chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])

            # Diagnostic: log the requested options so we can debug headless/incognito behavior
            # Defensive: if the user explicitly set headless=False, remove any headless args
            try:
                args_list = None
                if hasattr(chrome_options, 'arguments'):
                    args_list = chrome_options.arguments
                elif hasattr(chrome_options, '_arguments'):
                    args_list = chrome_options._arguments

                if args_list is not None:
                    filtered = []
                    for a in args_list:
                        if self.headless is False and (a.startswith('--headless') or a == '--headless'):
                            continue
                        if self.incognito is False and a == '--incognito':
                            continue
                        filtered.append(a)

                    # try to set back the filtered list to the options object
                    try:
                        if hasattr(chrome_options, 'arguments'):
                            chrome_options.arguments = filtered
                        elif hasattr(chrome_options, '_arguments'):
                            chrome_options._arguments = filtered
                    except Exception:
                        # not critical; continue
                        pass

            except Exception:
                # ignore filter errors
                pass

            # Build capabilities and ensure the final args list matches our filtered list
            try:
                caps = chrome_options.to_capabilities() or {}
            except Exception:
                caps = {}

            # Extract current args from capabilities and filter them explicitly
            current_args = []
            try:
                current_args = caps.get('goog:chromeOptions', {}).get('args', []) or []
            except Exception:
                current_args = []

            filtered_args = []
            for a in current_args:
                if self.headless is False and (a.startswith('--headless') or a == '--headless'):
                    continue
                if self.incognito is False and a == '--incognito':
                    continue
                filtered_args.append(a)

            # Ensure common args are present (disable-gpu etc.) if missing
            base_required = ['--disable-gpu', '--window-size=1366,768', '--log-level=3']
            for req in base_required:
                if req not in filtered_args:
                    filtered_args.append(req)

            # If the user explicitly requested incognito=True and it's not present, add it
            if self.incognito is True and '--incognito' not in filtered_args:
                filtered_args.append('--incognito')

            # If the user explicitly requested headless=True and it's not present, add it
            if self.headless is True and not any(x.startswith('--headless') for x in filtered_args):
                try:
                    filtered_args.insert(0, '--headless=new')
                except Exception:
                    filtered_args.insert(0, '--headless')

            # Put filtered args back into capabilities
            caps.setdefault('goog:chromeOptions', {})['args'] = filtered_args

            logger.info(f"Launching Chrome - headless={self.headless}, incognito={self.incognito}", str(caps.get('goog:chromeOptions', caps)))

            # Inisialisasi Chrome dengan lokasi driver using explicit capabilities to enforce args
            try:
                driver = webdriver.Chrome(service=Service(self.chromedriver_path), desired_capabilities=caps)
            except TypeError:
                # Fallback for selenium versions that don't accept desired_capabilities here
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

                # Tunggu halaman dan elemen render dengan polling setiap self.polling_interval
                # Cari elemen upload secara terus-menerus tanpa timeout (menghormati self.should_stop)
                upload_ready = False
                upload_selectors = [
                    "div[id='uploadArea'] input[type='file']",
                    "div[id='uploadArea'] input",
                    "div[class*='upload-area-root'] input[type='file']",
                    "div[class*='upload-area'] input[type='file']",
                    "div[class*='upload-area'] input",
                    "input[data-testid='input']",
                    "input[accept*='image/jpeg']"
                ]

                while not upload_ready and not self.should_stop:
                    try:
                        # Prefer document.readyState first
                        try:
                            ready = driver.execute_script("return document.readyState")
                        except Exception:
                            ready = None

                        # Check if any upload selector is present
                        found = False
                        for sel in upload_selectors:
                            try:
                                elems = driver.find_elements(By.CSS_SELECTOR, sel)
                                if elems and len(elems) > 0:
                                    found = True
                                    break
                            except Exception:
                                continue

                        if ready == 'complete' and found:
                            upload_ready = True
                            break
                    except Exception:
                        # ignore transient errors and poll again
                        pass

                    time.sleep(self.polling_interval)

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
                # Beri jeda singkat untuk memulai upload, selanjutnya kita akan polling untuk hasil enhancement
                time.sleep(self.polling_interval)

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
                
                # Menunggu gambar muncul - polling setiap self.polling_interval tanpa timeout
                start_time = time.time()

                found_image = False
                image_url = None

                # Menunggu gambar muncul
                processing_percent_range = percentages["processing"] - 5  # Dikurangi 5 yang sudah digunakan di atas

                while not found_image and not self.should_stop:
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
                # If we reach here and not found_image, but not stopped, loop will continue until found_image or should_stop
                # After loop, if should_stop handled above, otherwise proceed when found_image is True
                
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
                    
                    # Get output format from config
                    output_format = "png"  # Default to PNG
                    if self.config_manager:
                        output_format = self.config_manager.get_output_format()
                    
                    # Simpan file with the selected format
                    enhanced_path = os.path.join(output_folder, f"{file_name}_{timestamp}.{output_format}")
                    
                    # When downloading the image, convert to JPG if needed
                    if output_format == "jpg" and response.status_code == 200:
                        try:
                            # Try importing PIL - if it's not available, we'll fall back to PNG
                            try:
                                from PIL import Image
                                import io
                                HAS_PIL = True
                            except ImportError:
                                HAS_PIL = False
                                logger.peringatan("PIL tidak tersedia - tidak dapat konversi ke JPG", "Silakan install pillow: pip install pillow")
                                # Fallback to PNG
                                enhanced_path = os.path.join(output_folder, f"{file_name}_{timestamp}.png")
                                with open(enhanced_path, 'wb') as f:
                                    for chunk in response.iter_content(1024):
                                        f.write(chunk)
                                        
                            # If PIL is available, convert to JPG
                            if HAS_PIL:
                                # Save as PNG temporarily
                                temp_path = os.path.join(output_folder, f"{file_name}_temp_{timestamp}.png")
                                with open(temp_path, 'wb') as f:
                                    for chunk in response.iter_content(1024):
                                        f.write(chunk)
                                
                                # Convert to JPG with PIL
                                img = Image.open(temp_path)
                                rgb_img = img.convert('RGB')  # Convert to RGB (for PNG with transparency)
                                rgb_img.save(enhanced_path, quality=95)
                                
                                # Remove temporary file
                                if os.path.exists(temp_path):
                                    os.remove(temp_path)
                                    
                        except Exception as e:
                            logger.kesalahan(f"Error saat konversi ke JPG", f"{file_name} - {str(e)}")
                            # Fallback to PNG
                            enhanced_path = os.path.join(output_folder, f"{file_name}_{timestamp}.png")
                            with open(enhanced_path, 'wb') as f:
                                for chunk in response.iter_content(1024):
                                    f.write(chunk)
                    else:
                        # Original PNG saving code
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
                    logger.sukses(f"Berhasil menyimpan gambar enhancement", enhanced_path)
                    
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