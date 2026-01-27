from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import tempfile
import re
from selenium.common.exceptions import WebDriverException
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

def is_chrome_version_mismatch_exception(exc: Exception) -> bool:
    msg = str(exc) or ""
    if not msg:
        return False
    if re.search(r"This version of ChromeDriver only supports Chrome version\s*\d+", msg):
        return True
    if re.search(r"Current browser version is\s*\d+\.\d+\.\d+\.\d+", msg):
        return True
    return False


def open_chrome_for_update(chromedriver_path: str) -> None:
    logger.info(f"Membuka Chrome untuk cek update (otomatis) - path chromedriver: {chromedriver_path}")
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
        logger.sukses("Chrome berhasil dibuka untuk cek update (otomatis)")
    except Exception as e:
        logger.kesalahan("Gagal membuka Chrome untuk cek update (otomatis)", str(e))
        raise
    finally:
        os.environ['PATH'] = old_path

class ProgressSignal(QObject):
    progress = Signal(str, int)

class FileUpdateSignal(QObject):
    file_update = Signal(str, bool)

class ImageProcessor:
    def __init__(self, chromedriver_path: str = None, progress_callback: Callable = None, 
                 progress_signal: ProgressSignal = None, file_update_signal: FileUpdateSignal = None,
                 config_manager=None, headless: bool | None = None, incognito: bool | None = None):

        if chromedriver_path:
            self.chromedriver_path = chromedriver_path
        else:
            driver_filename = 'chromedriver.exe' if sys.platform == 'win32' else 'chromedriver'
            app_dir = os.path.dirname(os.path.abspath(__file__))
            base_dir = os.path.dirname(app_dir)
            self.chromedriver_path = os.path.join(base_dir, "driver", driver_filename)
        
        if not os.path.exists(self.chromedriver_path):
            logger.kesalahan(f"ChromeDriver tidak ditemukan di: {self.chromedriver_path}")
            raise FileNotFoundError(f"ChromeDriver tidak ditemukan di: {self.chromedriver_path}")
        
        if sys.platform != 'win32':
            import stat
            current_permissions = os.stat(self.chromedriver_path).st_mode
            if not (current_permissions & stat.S_IXUSR):
                logger.info(f"Menetapkan izin eksekusi pada ChromeDriver: {self.chromedriver_path}")
                os.chmod(self.chromedriver_path, current_permissions | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        self.progress_callback = progress_callback
        self.progress_signal = progress_signal
        self.file_update_signal = file_update_signal
        self.should_stop = False
        self.processing_thread = None
        self.total_processed = 0
        self.total_failed = 0
        self.results = []
        self.start_time = None
        self.end_time = None
        self.polling_interval = 1
        self.config_manager = config_manager
        self.headless = headless
        self.incognito = incognito
        self.batch_size = 1
        # activity timestamp used to detect processing hangs
        import time as _time
        self.last_activity_time = _time.time()
        
        
    def update_progress(self, message: str, percentage: int = None, current: int = None, total: int = None):
        if current is not None and total is not None:
            message = f"{message} [{current}/{total}]"

        def _shorten_filename(name: str, max_len: int = 40) -> str:
            base, ext = os.path.splitext(name)
            if len(base) + len(ext) <= max_len:
                return base + ext
            keep_len = max_len - len(ext) - 3
            if keep_len <= 0:
                return (base + ext)[:max_len-3] + '...'
            left = int(keep_len * 0.6)
            right = keep_len - left
            return base[:left] + '...' + base[-right:] + ext

        def _truncate_message(msg: str, max_total: int = 80) -> str:
            import re
            pattern = re.compile(r"([\w\W]{1,200}?\.(?:jpg|jpeg|png|bmp|gif))", re.IGNORECASE)
            def repl(m):
                fn = m.group(1)
                shortened = _shorten_filename(os.path.basename(fn), max_len=40)
                return shortened
            new_msg = pattern.sub(repl, msg)
            if len(new_msg) > max_total:
                return new_msg[:max_total-3] + '...'
            return new_msg

        message = _truncate_message(message)

        if self.progress_signal:
            self.progress_signal.progress.emit(message, percentage if percentage is not None else 0)
        elif self.progress_callback:
            self.progress_callback(message, percentage)

        # update last activity time to indicate progress
        try:
            import time as _time
            self.last_activity_time = _time.time()
        except Exception:
            pass

        is_milestone = percentage is not None and (percentage == 0 or percentage == 100 or percentage % 25 == 0)
        is_important_message = "berhasil" in message.lower() or "gagal" in message.lower() or "error" in message.lower()
        if is_milestone or is_important_message:
            logger.info(message, f"{percentage}%" if percentage is not None else None)
    
    def get_files_to_process(self, paths: List[str]) -> List[str]:
        all_files = []
        
        for path in paths:
            path_obj = Path(path)
            
            if path_obj.is_file() and self._is_image_file(path):
                all_files.append(str(path_obj))
            elif path_obj.is_dir():
                for ext in ['*.jpg', '*.jpeg', '*.png', '*.bmp', '*.gif']:
                    all_files.extend(glob.glob(os.path.join(path, '**', ext), recursive=True))
        
        return all_files
    
    def _is_image_file(self, file_path: str) -> bool:
        valid_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.gif']
        return Path(file_path).suffix.lower() in valid_extensions
    
    def start_processing(self, paths: List[str]):
        self.should_stop = False
        self.total_processed = 0
        self.total_failed = 0
        self.results = []
        self.start_time = datetime.now()
        
        files_to_process = self.get_files_to_process(paths)
        
        if not files_to_process:
            self.update_progress("Tidak ada file gambar ditemukan", 100)
            logger.warning("Tidak ada file gambar ditemukan", f"Paths: {', '.join(paths)}")
            return
        
        logger.info(f"Mulai memproses {len(files_to_process)} file gambar")
        
        self.processing_thread = threading.Thread(
            target=self._process_files,
            args=(files_to_process,)
        )
        self.processing_thread.daemon = True
        self.processing_thread.start()
    
    def stop_processing(self):
        if self.processing_thread and self.processing_thread.is_alive():
            logger.info("Menghentikan pemrosesan atas permintaan user")
            self.should_stop = True
            self.processing_thread.join(10)
    
    def _process_files(self, files: List[str]):
        total_files = len(files)

        batch_size = max(1, int(getattr(self, 'batch_size', 1) or 1))
        if batch_size > 20:
            batch_size = 20

        logger.info(f"Memproses {total_files} file dengan batch_size={batch_size}")
        for start in range(0, total_files, batch_size):
            if self.should_stop:
                logger.info("Pemrosesan dihentikan")
                break

            chunk = files[start:start + batch_size]
            drivers = [None] * len(chunk)
            chunk_results = [None] * len(chunk)

            for idx, file_path in enumerate(chunk):
                if self.should_stop:
                    break

                current_num = start + idx + 1
                file_name = Path(file_path).name

                if self.file_update_signal:
                    self.file_update_signal.file_update.emit(file_path, False)

                self.update_progress(
                    f"Memproses file",
                    percentage=int(( (start + idx) / total_files) * 100),
                    current=current_num,
                    total=total_files
                )

                try:
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

                        logger.info(f"Memulai Chrome untuk slot {idx} (headless={'Ya' if self.headless else 'Tidak'}, incognito={'Ya' if self.incognito else 'Tidak'})")
                        logger.debug(f"Chrome capabilities for slot {idx}: {str(caps.get('goog:chromeOptions', caps))}")

                        try:
                            driver = webdriver.Chrome(service=Service(self.chromedriver_path), desired_capabilities=caps)
                        except TypeError:
                            driver = webdriver.Chrome(service=Service(self.chromedriver_path), options=chrome_options)

                        drivers[idx] = driver
                        driver.get("https://picsart.com/id/ai-image-enhancer/")

                    except Exception as e:
                        logger.kesalahan("Gagal membuka browser untuk file", f"{file_name} - {str(e)}")
                        if is_chrome_version_mismatch_exception(e):
                            logger.peringatan("Versi Chrome/ChromeDriver tidak cocok terdeteksi; membuka Chrome untuk pengecekan update")
                            try:
                                open_chrome_for_update(self.chromedriver_path)
                            except Exception as oe:
                                logger.kesalahan("Gagal membuka Chrome untuk cek update setelah mendeteksi versi tidak cocok", str(oe))

                        chunk_results[idx] = {
                            "file_path": file_path,
                            "success": False,
                            "enhanced_path": None,
                            "error": str(e),
                            "start_time": datetime.now(),
                            "end_time": datetime.now(),
                            "duration": 0
                        }
                        drivers[idx] = None
                except Exception as e:
                    logger.kesalahan("Unexpected error during browser setup", str(e))

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
                for d in drivers:
                    try:
                        if d:
                            d.quit()
                    except Exception:
                        pass
                break

            for idx, d in enumerate(drivers):
                if d is None:
                    continue

                file_path = chunk[idx]
                file_name = Path(file_path).name

                input_file = None
                for selector in upload_selectors:
                    try:
                        input_file = d.find_element(By.CSS_SELECTOR, selector)
                        if input_file:
                            logger.info(f"Mengunggah file {file_name} untuk diproses (slot {idx})")
                            logger.debug(f"Upload selector for slot {idx}: {selector}")
                            break
                    except Exception:
                        continue

                if not input_file:
                    try:
                        input_file = d.execute_script("return document.querySelector('div[id=\'uploadArea\'] input') || document.querySelector('input[type=\'file\']') || document.querySelector('input[data-testid=\'input\']');")
                    except Exception:
                        input_file = None

                if not input_file:
                    logger.kesalahan("Area unggah tidak ditemukan", file_name)
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

                try:
                    input_file.send_keys(file_path)
                except Exception as e:
                    logger.kesalahan(f"Gagal mengunggah file {file_name}", str(e))
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

                time.sleep(self.polling_interval)

            pending = sum(1 for r in drivers if r is not None)
            start_times = [datetime.now() for _ in chunk]

            while pending > 0 and not self.should_stop:
                for idx, d in enumerate(drivers):
                    if d is None:
                        continue

                    file_path = chunk[idx]
                    file_name = Path(file_path).name

                    if chunk_results[idx] is not None:
                        continue

                    try:
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

                                chunk_results[idx] = {
                                    "file_path": file_path,
                                    "success": True,
                                    "enhanced_path": enhanced_path,
                                    "error": None,
                                    "start_time": start_times[idx],
                                    "end_time": datetime.now(),
                                    "duration": (datetime.now() - start_times[idx]).total_seconds()
                                }
                                # update activity timestamp
                                self.last_activity_time = time.time()

                                logger.sukses(f"Berhasil menyimpan gambar enhancement", enhanced_path)

                                current_num = start + idx + 1
                                self.update_progress(
                                    f"Gambar berhasil disimpan: {Path(enhanced_path).name}",
                                    percentage=int(((current_num) / total_files) * 100),
                                    current=current_num,
                                    total=total_files
                                )

                                try:
                                    d.quit()
                                except Exception:
                                    pass
                                drivers[idx] = None
                                pending -= 1
                            else:
                                chunk_results[idx] = {
                                    "file_path": file_path,
                                    "success": False,
                                    "enhanced_path": None,
                                    "error": f"Gagal mengunduh hasil. Status code: {response.status_code}",
                                    "start_time": start_times[idx],
                                    "end_time": datetime.now(),
                                    "duration": (datetime.now() - start_times[idx]).total_seconds()
                                }
                                # update activity timestamp
                                self.last_activity_time = time.time()
                                logger.kesalahan(f"Gagal mengunduh hasil. Status code: {response.status_code}", file_name)
                                try:
                                    d.quit()
                                except Exception:
                                    pass
                                drivers[idx] = None
                                pending -= 1

                        else:
                            continue

                    except Exception as e:
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
                        # update activity timestamp
                        self.last_activity_time = time.time()
                        try:
                            d.quit()
                        except Exception as inner_e:
                            logger.kesalahan("Gagal menutup driver slot", str(inner_e))
                        drivers[idx] = None
                        pending -= 1

                if pending > 0:
                    # detect processing hang based on last activity timestamp
                    hang_timeout = 300
                    if self.config_manager and hasattr(self.config_manager, 'get_processing_hang_timeout'):
                        try:
                            hang_timeout = int(self.config_manager.get_processing_hang_timeout())
                        except Exception as e:
                            logger.peringatan(f"Gagal membaca konfigurasi timeout: {e}")

                    idle = time.time() - getattr(self, 'last_activity_time', time.time())

                    if idle > hang_timeout:
                        logger.kesalahan("Timeout pemrosesan terdeteksi", f"Tidak ada aktivitas dalam {idle:.1f}s (> {hang_timeout}s)")
                        # mark remaining pending items as failed and attempt to close drivers
                        for j, d2 in enumerate(drivers):
                            if d2 is None:
                                continue
                            fp = chunk[j]
                            chunk_results[j] = {
                                "file_path": fp,
                                "success": False,
                                "enhanced_path": None,
                                "error": "Timeout: tidak ada progres dalam durasi yang ditentukan",
                                "start_time": start_times[j],
                                "end_time": datetime.now(),
                                "duration": (datetime.now() - start_times[j]).total_seconds()
                            }
                            try:
                                d2.quit()
                            except Exception as inner_e:
                                logger.kesalahan("Gagal menutup driver saat timeout", f"{fp} - {str(inner_e)}")
                            drivers[j] = None
                            pending -= 1
                        break

                    time.sleep(self.polling_interval)

            for idx, file_path in enumerate(chunk):
                res = chunk_results[idx]
                if res is None:
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

            # CLEANUP: ensure any remaining drivers are properly closed before next chunk/batch
            for idx_d, d in enumerate(drivers):
                if d is not None:
                    try:
                        logger.debug(f"Menutup driver slot {idx_d} pasca-batch cleanup")
                        d.quit()
                    except Exception as e:
                        logger.peringatan("Gagal menutup driver saat cleanup chunk", f"slot {idx_d} - {str(e)}")
                    drivers[idx_d] = None
        
        self.end_time = datetime.now()
        
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
        file_name = Path(file_path).name
        
        result = {
            "file_path": file_path,
            "success": False,
            "enhanced_path": None,
            "error": None,
            "start_time": datetime.now()
        }
        
        percentages = {"browser_setup": 5, "upload": 10, "processing": 65, "downloading": 15, "saving": 5}
        
        file_percent_size = 100 / total_files
        file_start_percent = (current_num - 1) * file_percent_size
        
        def calculate_global_percent(stage_percent):
            local_percent = stage_percent / 100 * file_percent_size
            return int(file_start_percent + local_percent)
        
        try:

            self.update_progress(
                f"Mempersiapkan chrome untuk file {Path(file_path).name}", 
                percentage=calculate_global_percent(percentages["browser_setup"] / 2),
                current=current_num, 
                total=total_files
            )
            

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


                    try:
                        if hasattr(chrome_options, 'arguments'):
                            chrome_options.arguments = filtered
                        elif hasattr(chrome_options, '_arguments'):
                            chrome_options._arguments = filtered
                    except Exception:

                        pass

            except Exception:

                pass


            try:
                caps = chrome_options.to_capabilities() or {}
            except Exception:
                caps = {}


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

            logger.info(f"Launching Chrome - headless={self.headless}, incognito={self.incognito}", str(caps.get('goog:chromeOptions', caps)))


            try:
                driver = webdriver.Chrome(service=Service(self.chromedriver_path), desired_capabilities=caps)
            except TypeError:

                driver = webdriver.Chrome(service=Service(self.chromedriver_path), options=chrome_options)
            except Exception as e:
                msg = str(e) or ""
                if 'cannot find Chrome binary' in msg or 'chrome not reachable' in msg.lower():
                    error_msg = "Chrome browser not found! Please install Google Chrome first.\n"
                    if sys.platform == 'darwin':
                        error_msg += "Install via: brew install --cask google-chrome\n"
                        error_msg += "Or download from: https://www.google.com/chrome/"
                    elif sys.platform == 'linux':
                        error_msg += "Install via: sudo apt install google-chrome-stable (Ubuntu/Debian)\n"
                        error_msg += "Or download from: https://www.google.com/chrome/"
                    logger.kesalahan("Chrome browser tidak ditemukan", error_msg)
                    result["error"] = error_msg
                    result["end_time"] = datetime.now()
                    result["duration"] = (result["end_time"] - result["start_time"]).total_seconds()
                    return result
                if is_chrome_version_mismatch_exception(e):
                    logger.peringatan("Versi Chrome/ChromeDriver tidak cocok terdeteksi; membuka Chrome untuk pengecekan update")
                    try:
                        open_chrome_for_update(self.chromedriver_path)
                    except Exception as oe:
                        logger.kesalahan("Gagal membuka Chrome untuk cek update setelah mendeteksi versi tidak cocok", str(oe))
                    result["error"] = "Chrome/ChromeDriver versi tidak cocok. Chrome dibuka untuk pengecekan update." 
                    result["end_time"] = datetime.now()
                    result["duration"] = (result["end_time"] - result["start_time"]).total_seconds()
                    return result
                else:
                    raise
            
            try:
                self.update_progress(
                    f"Membuka situs untuk file {Path(file_path).name}", 
                    percentage=calculate_global_percent(percentages["browser_setup"]),
                    current=current_num, 
                    total=total_files
                )
                
                driver.get("https://picsart.com/id/ai-image-enhancer/")


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

                        try:
                            ready = driver.execute_script("return document.readyState")
                        except Exception:
                            ready = None


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

                        pass

                    time.sleep(self.polling_interval)


                self.update_progress(
                    f"Mengunggah gambar: {Path(file_path).name}", 
                    percentage=calculate_global_percent(percentages["browser_setup"] + percentages["upload"] / 2),
                    current=current_num, 
                    total=total_files
                )
                

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
                            logger.info(f"Mengunggah file {file_name} untuk diproses")
                            logger.debug(f"Selector dicoba: {selector}")
                            break
                    except:
                        continue
                
                if not input_file:
                    logger.info("Mencari elemen unggah secara alternatif")
                    try:
                        input_file = driver.execute_script("""
                            return document.querySelector("div[id='uploadArea'] input") || 
                                   document.querySelector("input[type='file']") ||
                                   document.querySelector("input[data-testid='input']");
                        """)
                    except:
                        pass
                
                if not input_file:
                    debug_screenshot_path = os.path.join(os.path.dirname(file_path), "UPSCALE", "debug_screenshot.png")
                    os.makedirs(os.path.dirname(debug_screenshot_path), exist_ok=True)
                    driver.save_screenshot(debug_screenshot_path)
                    html_source = driver.page_source
                    debug_html_path = os.path.join(os.path.dirname(file_path), "UPSCALE", "page_source.html")
                    with open(debug_html_path, 'w', encoding='utf-8') as f:
                        f.write(html_source)
                    raise Exception("Tidak dapat menemukan elemen input file. Screenshot dan HTML source disimpan untuk debugging.")

                input_file.send_keys(file_path)
                time.sleep(self.polling_interval)

                self.update_progress(
                    f"File berhasil diunggah: {Path(file_path).name}", 
                    percentage=calculate_global_percent(percentages["browser_setup"] + percentages["upload"]),
                    current=current_num, 
                    total=total_files
                )
                

                self.update_progress(
                    f"Menunggu proses enhancement: {Path(file_path).name}", 
                    percentage=calculate_global_percent(percentages["browser_setup"] + percentages["upload"] + 5),
                    current=current_num, 
                    total=total_files
                )
                

                start_time = time.time()

                found_image = False
                image_url = None


                processing_percent_range = percentages["processing"] - 5

                if self.config_manager and hasattr(self.config_manager, 'get_max_wait_seconds'):
                    try:
                        max_wait_seconds = int(self.config_manager.get_max_wait_seconds())
                        if max_wait_seconds <= 0:
                            max_wait_seconds = 120
                    except Exception as e:
                        logger.peringatan("Invalid max_wait_seconds config, using default", str(e))
                        max_wait_seconds = 120
                else:
                    max_wait_seconds = 120

                logger.info(f"Menunggu hasil enhancement hingga {max_wait_seconds}s maksimal", file_name)

                start_time_wait = time.time()
                last_log_time = start_time_wait

                possible_selectors = [
                    'div[data-testid="EnhancedImage"] img',
                    'div[data-testid="EnhancedImage"][class*="widget-widgetContainer"] img',
                    'div[data-testid="EnhancedImage"] *[src]',
                    'img[alt*="enhanced"]',
                    'div[data-testid="EnhancedImage"]>div>img',
                    'div[data-testid="EnhancedImage"] picture img'
                ]

                while not found_image and not self.should_stop:
                    elapsed = time.time() - start_time_wait
                    if elapsed > max_wait_seconds:
                        output_folder = os.path.join(os.path.dirname(file_path), "UPSCALE")
                        os.makedirs(output_folder, exist_ok=True)
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        timeout_screenshot = os.path.join(output_folder, f"timeout_debug_{timestamp}.png")
                        timeout_html = os.path.join(output_folder, f"timeout_page_source_{timestamp}.html")
                        try:
                            driver.save_screenshot(timeout_screenshot)
                        except Exception as e:
                            logger.kesalahan("Gagal menyimpan screenshot pada timeout", f"{file_name} - {str(e)}")
                        try:
                            with open(timeout_html, 'w', encoding='utf-8') as f:
                                f.write(driver.page_source)
                        except Exception as e:
                            logger.kesalahan("Gagal menyimpan page source pada timeout", f"{file_name} - {str(e)}")

                        logger.kesalahan("Timeout menunggu hasil enhancement", f"{file_name} - tidak ada hasil setelah {int(elapsed)} detik. Screenshot: {timeout_screenshot}, HTML: {timeout_html}")
                        result["error"] = f"Timeout menunggu hasil enhancement setelah {int(elapsed)} detik"
                        result["end_time"] = datetime.now()
                        result["duration"] = (result["end_time"] - result["start_time"]).total_seconds()
                        try:
                            driver.quit()
                        except Exception as e:
                            logger.peringatan("Gagal menutup driver setelah timeout", f"{file_name} - {str(e)}")
                        return result

                    elapsed_percent = min(100, int(elapsed / 60 * 100))
                    process_stage_percent = (elapsed_percent / 100) * processing_percent_range
                    stage_percent = percentages["browser_setup"] + percentages["upload"] + 5 + process_stage_percent

                    self.update_progress(
                        f"Memproses enhancement: {Path(file_path).name} ({int(elapsed)} detik)", 
                        percentage=calculate_global_percent(stage_percent),
                        current=current_num, 
                        total=total_files
                    )

                    debug_summary = []

                    for selector in possible_selectors:
                        try:
                            img_elements = driver.execute_script(f"return Array.from(document.querySelectorAll('{selector}'))")
                        except Exception as e:
                            logger.kesalahan("Script error saat mengeksekusi selector", f"{file_name} - selector: {selector} - {str(e)}")
                            debug_summary.append({'selector': selector, 'error': str(e)})
                            continue

                        count = len(img_elements) if hasattr(img_elements, '__len__') else 0
                        src_types = []
                        for img in img_elements:
                            src = None
                            try:
                                src = img.get_attribute('src')
                            except Exception:
                                try:
                                    src = driver.execute_script('return arguments[0].getAttribute("src");', img)
                                except Exception as ee:
                                    logger.kesalahan("Gagal mengambil atribut src", f"{file_name} - selector: {selector} - {str(ee)}")
                                    src = None

                            if src:
                                if src.startswith('http'):
                                    image_url = src
                                    found_image = True
                                    src_types.append('http')
                                    break
                                elif src.startswith('blob:'):
                                    src_types.append('blob')
                                elif src.startswith('data:'):
                                    image_url = src
                                    found_image = True
                                    src_types.append('data')
                                    break
                                else:
                                    src_types.append('other')

                        debug_summary.append({'selector': selector, 'count': count, 'src_types': src_types})

                        if found_image:
                            break

                    if time.time() - last_log_time >= 5:
                        logger.debug(f"Menunggu hasil (debug): {file_name} - elapsed={int(elapsed)}s - selectors_checked={len(possible_selectors)} - debug={debug_summary}", file_name)
                        last_log_time = time.time()

                    time.sleep(self.polling_interval)
                if self.should_stop:
                    result["error"] = "Proses dihentikan oleh user"
                    logger.info("Proses dibatalkan oleh user", file_name)
                    return result

                

                logger.info(f"Menemukan gambar hasil", file_name)

                is_stream = False
                data_bytes = None

                if image_url.startswith('http'):
                    response = requests.get(image_url, stream=True)
                    if response.status_code != 200:
                        self.update_progress(
                            f"Gagal mengunduh gambar. Status code: {response.status_code}", 
                            percentage=calculate_global_percent(percentages["browser_setup"] + percentages["upload"] + percentages["processing"] + percentages["downloading"]),
                            current=current_num, 
                            total=total_files
                        )
                        logger.kesalahan(f"Gagal mengunduh hasil. Status code: {response.status_code}", file_name)
                        result["error"] = f"Gagal mengunduh gambar. Status code: {response.status_code}"
                        result["end_time"] = datetime.now()
                        result["duration"] = (result["end_time"] - result["start_time"]).total_seconds()
                        try:
                            driver.quit()
                        except Exception as e:
                            logger.peringatan("Gagal menutup driver setelah download error", f"{file_name} - {str(e)}")
                        return result
                    is_stream = True
                elif image_url.startswith('data:'):
                    try:
                        import base64
                        header, b64 = image_url.split(',', 1)
                        data_bytes = base64.b64decode(b64)
                    except Exception as e:
                        logger.kesalahan("Gagal decode data URL", f"{file_name} - {str(e)}")
                        result["error"] = f"Gagal decode data URL: {str(e)}"
                        result["end_time"] = datetime.now()
                        result["duration"] = (result["end_time"] - result["start_time"]).total_seconds()
                        try:
                            driver.quit()
                        except Exception as e:
                            logger.peringatan("Gagal menutup driver setelah decode error", f"{file_name} - {str(e)}")
                        return result
                elif image_url.startswith('blob:'):
                    try:
                        data_url = driver.execute_async_script("""
                            const blobUrl = arguments[0];
                            const callback = arguments[1];
                            fetch(blobUrl).then(r => r.blob()).then(blob => {
                                const fr = new FileReader();
                                fr.onload = function(){ callback(fr.result); }
                                fr.onerror = function(){ callback(null); }
                                fr.readAsDataURL(blob);
                            }).catch(()=>{ callback(null); });
                        """, image_url)
                        if data_url:
                            import base64
                            header, b64 = data_url.split(',', 1)
                            data_bytes = base64.b64decode(b64)
                        else:
                            logger.kesalahan("Gagal konversi blob ke data URL", file_name)
                            result["error"] = "Gagal konversi blob ke data URL"
                            result["end_time"] = datetime.now()
                            result["duration"] = (result["end_time"] - result["start_time"]).total_seconds()
                            try:
                                driver.quit()
                            except Exception as e:
                                logger.peringatan("Gagal menutup driver setelah blob konversi gagal", f"{file_name} - {str(e)}")
                            return result
                    except Exception as e:
                        logger.kesalahan("Gagal mengambil blob data", f"{file_name} - {str(e)}")
                        result["error"] = f"Gagal mengambil blob data: {str(e)}"
                        result["end_time"] = datetime.now()
                        result["duration"] = (result["end_time"] - result["start_time"]).total_seconds()
                        try:
                            driver.quit()
                        except Exception as e:
                            logger.peringatan("Gagal menutup driver setelah blob error", f"{file_name} - {str(e)}")
                        return result
                else:
                    logger.kesalahan("Unsupported image URL scheme", f"{file_name} - {image_url[:200]}")
                    result["error"] = "Unsupported image URL scheme"
                    result["end_time"] = datetime.now()
                    result["duration"] = (result["end_time"] - result["start_time"]).total_seconds()
                    try:
                        driver.quit()
                    except Exception as e:
                        logger.peringatan("Gagal menutup driver setelah unsupported URL", f"{file_name} - {str(e)}")
                    return result

                self.update_progress(
                    f"Mengunduh gambar enhancement: {Path(file_path).name}", 
                    percentage=calculate_global_percent(percentages["browser_setup"] + percentages["upload"] + percentages["processing"] + percentages["downloading"] / 2),
                    current=current_num, 
                    total=total_files
                )

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                file_name = Path(file_path).stem

                output_folder = os.path.join(os.path.dirname(file_path), "UPSCALE")
                os.makedirs(output_folder, exist_ok=True)

                output_format = "png"
                if self.config_manager:
                    output_format = self.config_manager.get_output_format()

                enhanced_path = os.path.join(output_folder, f"{file_name}_{timestamp}.{output_format}")

                if output_format == "jpg" and (is_stream or data_bytes is not None):
                    try:
                        try:
                            from PIL import Image
                            import io
                            HAS_PIL = True
                        except ImportError:
                            HAS_PIL = False
                            logger.peringatan("PIL tidak tersedia - tidak dapat konversi ke JPG", "Silakan install pillow: pip install pillow")
                            enhanced_path = os.path.join(output_folder, f"{file_name}_{timestamp}.png")
                            if is_stream:
                                with open(enhanced_path, 'wb') as f:
                                    for chunk in response.iter_content(1024):
                                        f.write(chunk)
                            else:
                                with open(enhanced_path, 'wb') as f:
                                    f.write(data_bytes)

                        if HAS_PIL:
                            temp_path = os.path.join(output_folder, f"{file_name}_temp_{timestamp}.png")
                            if is_stream:
                                with open(temp_path, 'wb') as f:
                                    for chunk in response.iter_content(1024):
                                        f.write(chunk)
                            else:
                                with open(temp_path, 'wb') as f:
                                    f.write(data_bytes)

                            img = Image.open(temp_path)
                            rgb_img = img.convert('RGB')
                            rgb_img.save(enhanced_path, quality=95)

                            if os.path.exists(temp_path):
                                os.remove(temp_path)
                    except Exception as e:
                        logger.kesalahan(f"Error saat konversi ke JPG", f"{file_name} - {str(e)}")
                        enhanced_path = os.path.join(output_folder, f"{file_name}_{timestamp}.png")
                        if is_stream:
                            with open(enhanced_path, 'wb') as f:
                                for chunk in response.iter_content(1024):
                                    f.write(chunk)
                        else:
                            with open(enhanced_path, 'wb') as f:
                                f.write(data_bytes)
                else:
                    if is_stream:
                        with open(enhanced_path, 'wb') as f:
                            for chunk in response.iter_content(1024):
                                f.write(chunk)
                    else:
                        with open(enhanced_path, 'wb') as f:
                            f.write(data_bytes)

                self.update_progress(
                    f"Gambar berhasil disimpan: {Path(enhanced_path).name}", 
                    percentage=calculate_global_percent(100),
                    current=current_num, 
                    total=total_files
                )

                logger.sukses(f"Berhasil menyimpan gambar enhancement", enhanced_path)
                
                result["success"] = True
                result["enhanced_path"] = enhanced_path
            finally:
                driver.quit()
                
        except Exception as e:

            logger.kesalahan(f"Error saat memproses gambar", f"{file_name} - {str(e)}")
            result["error"] = str(e)
            
        result["end_time"] = datetime.now()
        result["duration"] = (result["end_time"] - result["start_time"]).total_seconds()
        return result
        
    def get_statistics(self) -> Dict:
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
        

        for result in self.results:
            if "file_path" in result:
                folder = os.path.dirname(result["file_path"])
                stats["processed_folders"].add(folder)
                
        stats["processed_folders"] = list(stats["processed_folders"])
        return stats