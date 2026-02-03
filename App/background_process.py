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
import subprocess
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

def is_chrome_version_mismatch_exception(exc: Exception) -> bool:
    msg = str(exc) or ""
    if not msg:
        return False
    if re.search(r"This version of ChromeDriver only supports Chrome version\s*\d+", msg):
        return True
    if re.search(r"Current browser version is\s*\d+\.\d+\.\d+\.\d+", msg):
        return True
    return False


def extract_chrome_version_from_error(exc: Exception) -> int:
    """
    Extract Chrome major version from error message.
    
    Args:
        exc: The exception containing version mismatch error
        
    Returns:
        Chrome major version number, or None if not found
    """
    msg = str(exc) or ""
    
    # Try to extract from "Current browser version is X.X.X.X"
    match = re.search(r"Current browser version is\s*(\d+)\.(\d+)\.(\d+)\.(\d+)", msg)
    if match:
        return int(match.group(1))
    
    # Try to extract from "This version of ChromeDriver only supports Chrome version X"
    match = re.search(r"This version of ChromeDriver only supports Chrome version\s*(\d+)", msg)
    if match:
        return int(match.group(1))
    
    return None


def attempt_chromedriver_fix(base_dir: str, chrome_major_version: int = None) -> bool:
    """
    Attempt to download and install the correct ChromeDriver version.
    
    Args:
        base_dir: Base directory of the application
        chrome_major_version: Chrome major version to match
        
    Returns:
        True if successful, False otherwise
    """
    try:
        logger.info(f"Attempting to fix ChromeDriver version mismatch (Chrome v{chrome_major_version if chrome_major_version else 'auto'})")
        
        # Import here to avoid circular dependency
        from .tools_checker import download_chromedriver_for_chrome_version
        
        success = download_chromedriver_for_chrome_version(base_dir, chrome_major_version)
        
        if success:
            logger.sukses("ChromeDriver berhasil diperbarui dengan versi yang cocok")
            return True
        else:
            logger.peringatan("Gagal memperbarui ChromeDriver secara otomatis")
            return False
            
    except Exception as e:
        logger.kesalahan("Error saat mencoba memperbaiki ChromeDriver", str(e))
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

def initialize_chrome_driver_with_timeout(chromedriver_path: str, chrome_options, caps: dict = None, timeout: int = 30, max_retries: int = 3) -> webdriver.Chrome:
    """
    Initialize Chrome driver with timeout and retry mechanism.
    
    Args:
        chromedriver_path: Path to chromedriver executable
        chrome_options: Chrome options object
        caps: Capabilities dict (optional)
        timeout: Timeout in seconds for initialization
        max_retries: Maximum number of retry attempts
        
    Returns:
        Chrome WebDriver instance
        
    Raises:
        Exception: If initialization fails after all retries
    """
    def _init_driver():
        try:
            if caps:
                return webdriver.Chrome(service=Service(chromedriver_path), desired_capabilities=caps)
            else:
                return webdriver.Chrome(service=Service(chromedriver_path), options=chrome_options)
        except TypeError:
            # Fallback if desired_capabilities is not supported
            return webdriver.Chrome(service=Service(chromedriver_path), options=chrome_options)
    
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Inisialisasi Chrome (percobaan {attempt}/{max_retries}, timeout {timeout}s)")
            
            # Use ThreadPoolExecutor to run with timeout
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_init_driver)
                try:
                    driver = future.result(timeout=timeout)
                    logger.sukses(f"Chrome berhasil diinisialisasi pada percobaan {attempt}")
                    return driver
                except FutureTimeoutError:
                    logger.peringatan(f"Timeout inisialisasi Chrome pada percobaan {attempt} (>{timeout}s)")
                    # Try to cancel the future
                    future.cancel()
                    last_error = TimeoutError(f"Chrome initialization timeout after {timeout}s")
                    
                    # Wait a bit before retry
                    if attempt < max_retries:
                        time.sleep(2)
                except Exception as e:
                    logger.kesalahan(f"Error inisialisasi Chrome pada percobaan {attempt}", str(e))
                    last_error = e
                    
                    # Wait a bit before retry
                    if attempt < max_retries:
                        time.sleep(2)
        except Exception as e:
            logger.kesalahan(f"Error pada percobaan {attempt}", str(e))
            last_error = e
            
            # Wait a bit before retry
            if attempt < max_retries:
                time.sleep(2)
    
    # All retries failed
    error_msg = f"Gagal menginisialisasi Chrome setelah {max_retries} percobaan"
    if last_error:
        error_msg += f": {str(last_error)}"
    logger.kesalahan(error_msg)
    raise Exception(error_msg)

def compress_image_to_limit(image_path: str, max_size_mb: float = 10.0, output_path: str = None) -> str:
    """
    Compress image dynamically to stay under max_size_mb limit.
    
    Args:
        image_path: Path to input image
        max_size_mb: Maximum file size in MB (default 10MB)
        output_path: Optional output path, if None will create temp file
        
    Returns:
        Path to compressed image
    """
    try:
        from PIL import Image
        import io
    except ImportError:
        logger.peringatan("PIL tidak tersedia, tidak dapat kompresi gambar")
        return image_path
    
    max_size_bytes = int(max_size_mb * 1024 * 1024)
    original_size = os.path.getsize(image_path)
    
    if original_size <= max_size_bytes:
        logger.debug(f"File {os.path.basename(image_path)} sudah di bawah {max_size_mb}MB ({original_size / 1024 / 1024:.2f}MB)")
        return image_path
    
    logger.info(f"Mengompresi {os.path.basename(image_path)} dari {original_size / 1024 / 1024:.2f}MB ke <{max_size_mb}MB")
    
    # Load image
    img = Image.open(image_path)
    
    # Convert to RGB if necessary
    if img.mode in ('RGBA', 'LA', 'P'):
        background = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'P':
            img = img.convert('RGBA')
        background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
        img = background
    elif img.mode != 'RGB':
        img = img.convert('RGB')
    
    # Determine output path
    if output_path is None:
        temp_dir = os.path.dirname(image_path)
        base_name = Path(image_path).stem
        output_path = os.path.join(temp_dir, f"{base_name}_compressed.jpg")
    
    # Binary search for optimal quality
    min_quality = 10
    max_quality = 95
    best_quality = max_quality
    
    while min_quality <= max_quality:
        mid_quality = (min_quality + max_quality) // 2
        
        # Try compression at this quality
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=mid_quality, optimize=True)
        compressed_size = buffer.tell()
        
        if compressed_size <= max_size_bytes:
            # This quality works, try higher
            best_quality = mid_quality
            min_quality = mid_quality + 1
        else:
            # Too large, try lower quality
            max_quality = mid_quality - 1
    
    # Save with best quality found
    img.save(output_path, format='JPEG', quality=best_quality, optimize=True)
    final_size = os.path.getsize(output_path)
    
    logger.sukses(f"Kompresi berhasil: {original_size / 1024 / 1024:.2f}MB → {final_size / 1024 / 1024:.2f}MB (quality={best_quality})")
    
    return output_path

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
        # Multi-level upscale support (2x, 4x, 6x)
        self.upscale_level = "2x"
        # Track actual file count for stats (not inflated by multi-pass)
        self.actual_file_count = 0
        # Track converted files for cleanup
        self.converted_files_to_cleanup = []
        # Chrome initialization settings
        self.chrome_init_timeout = 30  # timeout per attempt
        self.chrome_init_retries = 3   # max retry attempts
        self.page_load_timeout = 30    # page load timeout
        self.global_driver_tracker = []
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
                # Scan for all possible image formats
                for ext in ['*.jpg', '*.jpeg', '*.png', '*.bmp', '*.gif', '*.tif', '*.tiff', 
                           '*.webp', '*.avif', '*.ico', '*.pcx', '*.ppm', '*.sgi', '*.tga']:
                    all_files.extend(glob.glob(os.path.join(path, '**', ext), recursive=True))
        
        return all_files
    
    def _is_image_file(self, file_path: str) -> bool:
        """Check if file is a supported image format (including all Pillow-supported formats)"""
        try:
            from PIL import Image
            # Try to open with PIL to verify it's a valid image
            with Image.open(file_path) as img:
                # Just verify we can open it
                _ = img.format
                return True
        except Exception:
            # Fallback to extension check
            valid_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tif', '.tiff', '.webp', '.avif', '.ico', '.pcx', '.ppm', '.sgi', '.tga']
            return Path(file_path).suffix.lower() in valid_extensions

    def _convert_to_standard_format(self, file_path: str) -> Tuple[str, bool]:
        """
        Convert image to PNG if it's not in a web-standard format (JPG/PNG/GIF).
        
        Args:
            file_path: Path to the image file
            
        Returns:
            Tuple of (converted_path, was_converted)
            - converted_path: Path to converted file (or original if no conversion needed)
            - was_converted: True if file was converted, False if original was used
        """
        try:
            from PIL import Image
        except ImportError:
            logger.peringatan("PIL tidak tersedia, tidak dapat konversi format")
            return file_path, False
        
        # Check if already in standard format
        ext = Path(file_path).suffix.lower()
        if ext in ['.jpg', '.jpeg', '.png', '.gif']:
            return file_path, False
        
        # Need to convert
        logger.info(f"Mengonversi {os.path.basename(file_path)} dari {ext} ke PNG")
        
        try:
            img = Image.open(file_path)
            
            # Prepare output path
            output_dir = os.path.dirname(file_path)
            base_name = Path(file_path).stem
            converted_path = os.path.join(output_dir, f"{base_name}_converted.png")
            
            # Convert RGBA/LA/P modes properly
            if img.mode in ('RGBA', 'LA'):
                # Keep transparency
                img.save(converted_path, format='PNG', optimize=True)
            elif img.mode == 'P':
                # Palette mode - convert to RGBA to preserve transparency if exists
                img = img.convert('RGBA')
                img.save(converted_path, format='PNG', optimize=True)
            elif img.mode in ('L', 'RGB'):
                # Grayscale or RGB - direct conversion
                img.save(converted_path, format='PNG', optimize=True)
            else:
                # Other modes - convert to RGB first
                img = img.convert('RGB')
                img.save(converted_path, format='PNG', optimize=True)
            
            img.close()
            
            logger.sukses(f"Konversi berhasil: {os.path.basename(file_path)} → {os.path.basename(converted_path)}")
            return converted_path, True
            
        except Exception as e:
            logger.kesalahan(f"Gagal konversi {os.path.basename(file_path)}", str(e))
            return file_path, False
    
    def _cleanup_converted_files(self):
        """Cleanup temporary converted files (e.g., TIF/AVIF/WEBP converted to PNG)"""
        if not self.converted_files_to_cleanup:
            return
        
        logger.info(f"Membersihkan {len(self.converted_files_to_cleanup)} file hasil konversi...")
        
        for file_path in self.converted_files_to_cleanup:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.debug(f"Berhasil menghapus file konversi: {os.path.basename(file_path)}")
            except Exception as e:
                logger.peringatan(f"Gagal menghapus file konversi {os.path.basename(file_path)}", str(e))
        
        # Clear the list after cleanup
        self.converted_files_to_cleanup = []
        logger.sukses(f"Cleanup file konversi selesai")

    def _get_upscale_passes(self) -> int:
        """Get number of upscale passes based on upscale_level (2x=1, 4x=2, 6x=3)"""
        return {"2x": 1, "4x": 2, "6x": 3}.get(self.upscale_level, 1)

    def _get_output_folder(self, file_path: str) -> str:
        """
        Determine output folder based on current processing state.
        Uses temp_UPSCALE for intermediate passes, UPSCALE for final pass.
        """
        use_temp = getattr(self, '_current_use_temp', False)
        folder_name = "temp_UPSCALE" if use_temp else "UPSCALE"
        
        # For intermediate passes, we need to determine the original source directory
        # If file is in temp_UPSCALE, get the parent's parent
        file_dir = os.path.dirname(file_path)
        dir_name = os.path.basename(file_dir)
        
        if dir_name == "temp_UPSCALE":
            # File is from previous temp pass, output to same level (parent's temp_UPSCALE or UPSCALE)
            parent_dir = os.path.dirname(file_dir)
            return os.path.join(parent_dir, folder_name)
        else:
            # File is from original source
            return os.path.join(file_dir, folder_name)

    def _get_original_base_name(self, file_path: str) -> str:
        """
        Extract the original base name from a file path, stripping any timestamp suffix.
        This is important for multi-pass upscaling to maintain consistent naming.
        
        For example:
        - "image.png" -> "image"
        - "image_20260203_143022.png" -> "image"
        """
        import re
        file_stem = Path(file_path).stem
        
        # Pattern to match _YYYYMMDD_HHMMSS at the end
        timestamp_pattern = re.compile(r'_\d{8}_\d{6}$')
        return timestamp_pattern.sub('', file_stem)
    
    def start_processing(self, paths: List[str]):
        self.should_stop = False
        self.total_processed = 0
        self.total_failed = 0
        self.results = []
        self.start_time = datetime.now()
        self.converted_files_to_cleanup = []
        self.global_driver_tracker.clear()
        
        files_to_process = self.get_files_to_process(paths)
        
        if not files_to_process:
            self.update_progress("Tidak ada file gambar ditemukan", 100)
            logger.warning("Tidak ada file gambar ditemukan", f"Paths: {', '.join(paths)}")
            return
        
        # Convert non-standard formats to PNG
        logger.info("Memeriksa format gambar yang perlu dikonversi...")
        converted_files = []
        for file_path in files_to_process:
            converted_path, was_converted = self._convert_to_standard_format(file_path)
            converted_files.append(converted_path)
            if was_converted:
                self.converted_files_to_cleanup.append(converted_path)
        
        files_to_process = converted_files
        
        # Store actual file count for stats (not multiplied by passes)
        self.actual_file_count = len(files_to_process)
        upscale_passes = self._get_upscale_passes()
        
        logger.info(f"Mulai memproses {len(files_to_process)} file gambar dengan upscale {self.upscale_level} ({upscale_passes} pass)")
        
        self.processing_thread = threading.Thread(
            target=self._process_files_multilevel,
            args=(files_to_process,)
        )
        self.processing_thread.daemon = True
        self.processing_thread.start()
    
    def stop_processing(self):
        if self.processing_thread and self.processing_thread.is_alive():
            logger.info("Menghentikan pemrosesan atas permintaan user")
            self.should_stop = True
            
            logger.info(f"Force closing {len(self.global_driver_tracker)} Chrome instances...")
            closed_count = 0
            for driver in self.global_driver_tracker:
                if driver is not None:
                    try:
                        driver.quit()
                        closed_count += 1
                    except Exception:
                        pass
            self.global_driver_tracker.clear()
            logger.sukses(f"{closed_count} Chrome instances ditutup paksa")
            
            self.processing_thread.join(10)
            
            logger.info("Mereset state setelah stop...")
            self.should_stop = False
            
            self._cleanup_converted_files()
            
            import gc
            gc.collect()
            logger.info("Pemrosesan berhasil dihentikan dan state direset")

    def _process_files_multilevel(self, files: List[str]):
        """
        Multi-level upscale processing wrapper.
        For 2x: single pass, save directly to UPSCALE folder
        For 4x: two passes (2x -> temp_UPSCALE -> 2x -> UPSCALE)
        For 6x: three passes (2x -> temp_UPSCALE -> 2x -> temp_UPSCALE -> 2x -> UPSCALE)
        """
        import shutil
        
        upscale_passes = self._get_upscale_passes()
        total_files = len(files)
        
        logger.info(f"Memulai upscale {self.upscale_level} untuk {total_files} file ({upscale_passes} pass)")
        
        if upscale_passes == 1:
            # Standard 2x processing - direct to UPSCALE folder
            self._process_files(files, current_pass=1, total_passes=1, use_temp=False)
            
            # Cleanup converted files after single pass
            self._cleanup_converted_files()
            return
        
        # Multi-pass processing (4x or 6x)
        # Track original file info for each file - keyed by index for consistent ordering
        original_file_info = []
        for f in files:
            original_file_info.append({
                'original_path': f,
                'original_dir': os.path.dirname(f),
                'original_name': Path(f).stem,
                'original_ext': Path(f).suffix,
                'current_path': f  # Will be updated after each pass
            })
        
        current_files = files[:]
        
        for pass_num in range(1, upscale_passes + 1):
            if self.should_stop:
                logger.info("Proses multi-level dihentikan oleh user")
                break
            
            is_final_pass = (pass_num == upscale_passes)
            
            logger.info(f"Pass {pass_num}/{upscale_passes} untuk upscale {self.upscale_level}")
            self.update_progress(
                f"Upscale {self.upscale_level} - Pass {pass_num}/{upscale_passes}",
                percentage=int(((pass_num - 1) / upscale_passes) * 100)
            )
            
            # Process current batch
            self._process_files(
                current_files, 
                current_pass=pass_num, 
                total_passes=upscale_passes,
                use_temp=not is_final_pass  # Use temp folder for intermediate passes
            )
            
            if self.should_stop:
                break
            
            if not is_final_pass:
                # Prepare files for next pass from temp_UPSCALE folders
                next_files = []
                for idx, info in enumerate(original_file_info):
                    orig_dir = info['original_dir']
                    orig_name = info['original_name']
                    current_path = info['current_path']
                    
                    # Determine where to look for the output
                    # If current file is in temp_UPSCALE, look there
                    current_file_dir = os.path.dirname(current_path)
                    if os.path.basename(current_file_dir) == "temp_UPSCALE":
                        # File was from temp_UPSCALE, look in same temp_UPSCALE (same source dir)
                        search_dir = os.path.join(os.path.dirname(current_file_dir), "temp_UPSCALE")
                    else:
                        # File was from original dir
                        search_dir = os.path.join(orig_dir, "temp_UPSCALE")
                    
                    if os.path.exists(search_dir):
                        # Find files matching the original name pattern (name_timestamp.ext)
                        matching_files = []
                        for f in os.listdir(search_dir):
                            fpath = os.path.join(search_dir, f)
                            if os.path.isfile(fpath):
                                # Get the base part of the filename (before timestamp)
                                fname_stem = Path(f).stem
                                # The saved file is named: originalname_YYYYMMDD_HHMMSS.ext
                                # So we check if it starts with the original name followed by underscore
                                if fname_stem.startswith(orig_name + "_") or fname_stem == orig_name:
                                    matching_files.append(fpath)
                        
                        if matching_files:
                            # Get the most recent file
                            matching_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                            next_files.append(matching_files[0])
                            # Update info for tracking
                            original_file_info[idx]['current_path'] = matching_files[0]
                            logger.info(f"Pass {pass_num} selesai untuk {orig_name}", matching_files[0])
                        else:
                            logger.kesalahan(f"Tidak ditemukan hasil upscale untuk pass {pass_num}", f"{orig_name} di {search_dir}")
                    else:
                        logger.kesalahan(f"Folder temp_UPSCALE tidak ditemukan untuk pass {pass_num}", search_dir)
                
                current_files = next_files
        
        # After final pass, cleanup temp_UPSCALE folders
        if not self.should_stop:
            logger.info("Membersihkan folder temp_UPSCALE...")
            cleaned_dirs = set()
            for info in original_file_info:
                temp_upscale_dir = os.path.join(info['original_dir'], "temp_UPSCALE")
                if temp_upscale_dir not in cleaned_dirs and os.path.exists(temp_upscale_dir):
                    try:
                        shutil.rmtree(temp_upscale_dir)
                        logger.info(f"Berhasil menghapus temp_UPSCALE", temp_upscale_dir)
                        cleaned_dirs.add(temp_upscale_dir)
                    except Exception as e:
                        logger.kesalahan(f"Gagal menghapus temp_UPSCALE", f"{temp_upscale_dir} - {str(e)}")
            
            # Cleanup converted files (format conversions)
            self._cleanup_converted_files()
            
            logger.sukses(f"Upscale {self.upscale_level} selesai untuk {total_files} file")
    
    def _process_files(self, files: List[str], current_pass: int = 1, total_passes: int = 1, use_temp: bool = False):
        total_files = len(files)

        batch_size = max(1, int(getattr(self, 'batch_size', 1) or 1))
        if batch_size > 20:
            batch_size = 20

        pass_info = f"[Pass {current_pass}/{total_passes}] " if total_passes > 1 else ""
        logger.info(f"{pass_info}Memproses {total_files} file dengan batch_size={batch_size}")
        
        # Store use_temp flag for this processing run
        self._current_use_temp = use_temp
        self._current_pass = current_pass
        self._total_passes = total_passes
        
        for start in range(0, total_files, batch_size):
            if self.should_stop:
                logger.info("Pemrosesan dihentikan")
                break

            batch_num = (start // batch_size) + 1
            total_batches = (total_files + batch_size - 1) // batch_size
            logger.info(f"=== Batch {batch_num}/{total_batches}: Memproses item {start + 1} - {min(start + batch_size, total_files)} ===")
            logger.clear_log()

            chunk = files[start:start + batch_size]
            drivers = [None] * len(chunk)
            chunk_results = [None] * len(chunk)
            
            # Track all drivers created in this batch for guaranteed cleanup
            batch_driver_tracker = []

            for idx, file_path in enumerate(chunk):
                if self.should_stop:
                    logger.info("Stop diminta saat inisialisasi browser, membatalkan...")
                    # Mark remaining as failed
                    for remaining_idx in range(idx, len(chunk)):
                        chunk_results[remaining_idx] = {
                            "file_path": chunk[remaining_idx],
                            "success": False,
                            "enhanced_path": None,
                            "error": "Dihentikan oleh user sebelum diproses",
                            "start_time": datetime.now(),
                            "end_time": datetime.now(),
                            "duration": 0
                        }
                    break

                current_num = start + idx + 1
                file_name = Path(file_path).name

                if self.file_update_signal:
                    self.file_update_signal.file_update.emit(file_path, False)

                # Calculate progress considering multi-pass
                pass_progress = (start + idx) / total_files
                if total_passes > 1:
                    overall_progress = ((current_pass - 1) + pass_progress) / total_passes
                    pass_info = f"[{self.upscale_level} Pass {current_pass}/{total_passes}] "
                else:
                    overall_progress = pass_progress
                    pass_info = ""

                self.update_progress(
                    f"{pass_info}Memproses file",
                    percentage=int(overall_progress * 100),
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

                        # Basic options
                        chrome_options.add_argument("--disable-gpu")
                        chrome_options.add_argument("--window-size=1366,768")
                        chrome_options.add_argument("--log-level=3")
                        if self.incognito:
                            chrome_options.add_argument("--incognito")
                        
                        # Memory and performance optimization
                        chrome_options.add_argument("--disable-dev-shm-usage")
                        chrome_options.add_argument("--no-sandbox")
                        chrome_options.add_argument("--disable-extensions")
                        chrome_options.add_argument("--disable-plugins")
                        chrome_options.add_argument("--disable-background-networking")
                        chrome_options.add_argument("--disable-default-apps")
                        chrome_options.add_argument("--disable-sync")
                        chrome_options.add_argument("--metrics-recording-only")
                        chrome_options.add_argument("--mute-audio")
                        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
                        chrome_options.add_experimental_option('useAutomationExtension', False)

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

                        # Use timeout and retry mechanism for Chrome initialization
                        driver = initialize_chrome_driver_with_timeout(
                            chromedriver_path=self.chromedriver_path,
                            chrome_options=chrome_options,
                            caps=caps,
                            timeout=self.chrome_init_timeout,
                            max_retries=self.chrome_init_retries
                        )

                        drivers[idx] = driver
                        batch_driver_tracker.append(driver)
                        self.global_driver_tracker.append(driver)
                        
                        # Navigate to URL with timeout protection and retry
                        url_load_success = False
                        max_url_retries = 3
                        url_retry_delay = 2
                        
                        for url_attempt in range(1, max_url_retries + 1):
                            try:
                                logger.info(f"Membuka URL untuk slot {idx} (percobaan {url_attempt}/{max_url_retries})")
                                driver.set_page_load_timeout(self.page_load_timeout)
                                driver.get("https://picsart.com/id/ai-image-enhancer/")
                                logger.sukses(f"URL berhasil dimuat untuk slot {idx} pada percobaan {url_attempt}")
                                url_load_success = True
                                break  # Success, exit retry loop
                            except Exception as nav_error:
                                logger.peringatan(f"Percobaan {url_attempt}/{max_url_retries} gagal untuk slot {idx}: {str(nav_error)[:100]}")
                                
                                if url_attempt < max_url_retries:
                                    logger.info(f"Mencoba lagi dalam {url_retry_delay} detik...")
                                    time.sleep(url_retry_delay)
                                    # Try to refresh driver state
                                    try:
                                        driver.execute_script("window.stop();")
                                    except Exception:
                                        pass
                                else:
                                    # All retries failed
                                    logger.kesalahan(f"Gagal load URL untuk slot {idx} setelah {max_url_retries} percobaan")
                        
                        # If URL loading failed after all retries, close driver and mark as failed
                        if not url_load_success:
                            try:
                                driver.quit()
                                logger.info(f"Driver slot {idx} ditutup karena gagal load URL setelah {max_url_retries} percobaan")
                            except Exception:
                                pass
                            drivers[idx] = None
                            chunk_results[idx] = {
                                "file_path": file_path,
                                "success": False,
                                "enhanced_path": None,
                                "error": f"Timeout membuka URL setelah {max_url_retries} percobaan",
                                "start_time": datetime.now(),
                                "end_time": datetime.now(),
                                "duration": 0
                            }
                            # Continue to next file in chunk
                            continue

                    except Exception as e:
                        logger.kesalahan("Gagal membuka browser untuk file", f"{file_name} - {str(e)}")
                        if is_chrome_version_mismatch_exception(e):
                            logger.peringatan("Versi Chrome/ChromeDriver tidak cocok terdeteksi")
                            
                            # Extract Chrome version from error
                            chrome_version = extract_chrome_version_from_error(e)
                            
                            # Get base directory
                            app_dir = os.path.dirname(os.path.abspath(__file__))
                            base_dir = os.path.dirname(app_dir)
                            
                            # Attempt to download correct driver
                            logger.info(f"Mencoba mengunduh ChromeDriver yang sesuai dengan Chrome v{chrome_version if chrome_version else 'terinstall'}")
                            fix_success = attempt_chromedriver_fix(base_dir, chrome_version)
                            
                            if fix_success:
                                logger.sukses("ChromeDriver berhasil diperbarui, silakan coba lagi")
                                # Update the chromedriver path for this instance
                                driver_filename = 'chromedriver.exe' if sys.platform == 'win32' else 'chromedriver'
                                self.chromedriver_path = os.path.join(base_dir, "driver", driver_filename)
                            else:
                                logger.peringatan("Gagal memperbarui ChromeDriver otomatis, mencoba membuka Chrome untuk update manual")
                                try:
                                    open_chrome_for_update(self.chromedriver_path)
                                except Exception as oe:
                                    logger.kesalahan("Gagal membuka Chrome untuk cek update", str(oe))

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
                        
                        # Ensure any partial driver is cleaned up
                        try:
                            if 'driver' in locals() and driver is not None:
                                driver.quit()
                                logger.info(f"Driver untuk slot {idx} berhasil dibersihkan setelah error")
                        except Exception as cleanup_error:
                            logger.peringatan(f"Error saat cleanup driver slot {idx}: {str(cleanup_error)}")
                            
                except Exception as e:
                    logger.kesalahan("Unexpected error during browser setup", str(e))
                    chunk_results[idx] = {
                        "file_path": file_path,
                        "success": False,
                        "enhanced_path": None,
                        "error": f"Unexpected error: {str(e)}",
                        "start_time": datetime.now(),
                        "end_time": datetime.now(),
                        "duration": 0
                    }
                    drivers[idx] = None

            upload_selectors = [
                "div[id='uploadArea'] input[type='file']",
                "div[id='uploadArea'] input",
                "div[class*='upload-area-root'] input[type='file']",
                "div[class*='upload-area'] input[type='file']",
                "div[class*='upload-area'] input",
                "input[data-testid='input']",
                "input[accept*='image/jpeg']"
            ]

            # Wait for page to be ready with timeout
            all_ready = False
            page_ready_timeout = 60  # 60 seconds timeout for page ready
            page_ready_start = time.time()
            
            while not all_ready and not self.should_stop:
                # Check timeout
                if time.time() - page_ready_start > page_ready_timeout:
                    logger.peringatan(f"Timeout menunggu page ready setelah {page_ready_timeout}s, melanjutkan...")
                    break
                
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

            # Check if stopped after page ready phase
            if self.should_stop:
                logger.info("Stop diminta setelah page ready, menutup semua browser...")
                for idx_d, d in enumerate(drivers):
                    try:
                        if d:
                            d.quit()
                            logger.debug(f"Browser slot {idx_d} ditutup")
                    except Exception as e:
                        logger.peringatan(f"Error menutup browser slot {idx_d}: {str(e)}")
                    drivers[idx_d] = None
                # Mark all in this chunk as failed due to stop
                for idx_mark, file_mark in enumerate(chunk):
                    if chunk_results[idx_mark] is None:
                        chunk_results[idx_mark] = {
                            "file_path": file_mark,
                            "success": False,
                            "enhanced_path": None,
                            "error": "Dihentikan oleh user",
                            "start_time": datetime.now(),
                            "end_time": datetime.now(),
                            "duration": 0
                        }
                break

            # Start upload phase
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

                # Check file size and compress if needed (>10MB)
                upload_file_path = file_path
                compressed_file = None
                file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
                
                if file_size_mb > 10.0:
                    logger.info(f"File {file_name} terlalu besar ({file_size_mb:.2f}MB), mengompresi...")
                    try:
                        compressed_file = compress_image_to_limit(file_path, max_size_mb=9.5)  # 9.5MB to be safe
                        upload_file_path = compressed_file
                        logger.sukses(f"File berhasil dikompres untuk upload")
                    except Exception as comp_error:
                        logger.peringatan(f"Gagal mengompresi file, mencoba upload original: {str(comp_error)}")
                        upload_file_path = file_path

                try:
                    input_file.send_keys(upload_file_path)
                    
                    # Wait a moment and check for file size error
                    time.sleep(2)
                    try:
                        error_element = d.find_element(By.CSS_SELECTOR, "span[data-testid='text'][class*='text-root']")
                        error_text = error_element.text if error_element else ""
                        
                        if "exceeds max size" in error_text.lower() or "10 mb" in error_text.lower():
                            logger.kesalahan(f"File {file_name} melebihi batas ukuran: {error_text}")
                            
                            # If we haven't tried compression yet, try now
                            if compressed_file is None and file_size_mb > 10.0:
                                logger.info("Mencoba dengan versi terkompres...")
                                try:
                                    compressed_file = compress_image_to_limit(file_path, max_size_mb=9.0)  # Even smaller
                                    # Clear the input and try again
                                    input_file.clear()
                                    input_file.send_keys(compressed_file)
                                    time.sleep(2)
                                    logger.sukses("Upload dengan file terkompres berhasil")
                                except Exception as retry_error:
                                    logger.kesalahan(f"Gagal upload file terkompres: {str(retry_error)}")
                                    raise
                            else:
                                raise Exception(f"File terlalu besar bahkan setelah kompresi: {error_text}")
                    except Exception as check_error:
                        # No error found or error checking failed, continue normally
                        if "exceeds max size" not in str(check_error).lower():
                            pass  # No size error, continue
                        else:
                            raise  # Re-raise size error
                    
                    # Cleanup compressed temp file if created
                    if compressed_file and compressed_file != file_path and os.path.exists(compressed_file):
                        try:
                            # Don't delete yet, might need for retry
                            pass
                        except Exception:
                            pass
                            
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

            # Check if stopped after upload phase
            if self.should_stop:
                logger.info("Stop diminta setelah upload, membersihkan...")
                for idx_clean, d_clean in enumerate(drivers):
                    if d_clean is not None:
                        try:
                            d_clean.quit()
                        except Exception:
                            pass
                        drivers[idx_clean] = None
                for idx_mark, file_mark in enumerate(chunk):
                    if chunk_results[idx_mark] is None:
                        chunk_results[idx_mark] = {
                            "file_path": file_mark,
                            "success": False,
                            "enhanced_path": None,
                            "error": "Dihentikan oleh user setelah upload",
                            "start_time": datetime.now(),
                            "end_time": datetime.now(),
                            "duration": 0
                        }
                break

            pending = sum(1 for r in drivers if r is not None)
            start_times = [datetime.now() for _ in chunk]

            while pending > 0 and not self.should_stop:
                for idx, d in enumerate(drivers):
                    if d is None:
                        continue
                    
                    # Validate driver is still in good state
                    try:
                        current_url = d.current_url
                        # Check for invalid states (data: URL indicates problem)
                        if current_url and current_url.startswith("data:"):
                            logger.peringatan(f"Driver slot {idx} dalam state invalid (data: URL), menutup...")
                            try:
                                d.quit()
                            except Exception:
                                pass
                            drivers[idx] = None
                            chunk_results[idx] = {
                                "file_path": chunk[idx],
                                "success": False,
                                "enhanced_path": None,
                                "error": "Browser dalam state invalid (data: URL)",
                                "start_time": start_times[idx],
                                "end_time": datetime.now(),
                                "duration": (datetime.now() - start_times[idx]).total_seconds()
                            }
                            pending -= 1
                            continue
                    except Exception as url_check_error:
                        # If we can't check URL, driver might be dead
                        logger.peringatan(f"Tidak dapat cek URL driver slot {idx}, mungkin sudah mati")
                        if "invalid session id" in str(url_check_error).lower() or "no such window" in str(url_check_error).lower():
                            try:
                                d.quit()
                            except Exception:
                                pass
                            drivers[idx] = None
                            if chunk_results[idx] is None:
                                chunk_results[idx] = {
                                    "file_path": chunk[idx],
                                    "success": False,
                                    "enhanced_path": None,
                                    "error": "Browser session hilang",
                                    "start_time": start_times[idx],
                                    "end_time": datetime.now(),
                                    "duration": (datetime.now() - start_times[idx]).total_seconds()
                                }
                            pending -= 1
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
                                # Use original base name (without timestamp suffix) for consistent naming
                                base_name = self._get_original_base_name(file_path)
                                output_folder = self._get_output_folder(file_path)
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
            
            # Check if stopped during processing
            if self.should_stop:
                logger.info("Proses dihentikan, membersihkan drivers yang tersisa...")
                for idx_stop, d_stop in enumerate(drivers):
                    if d_stop is not None:
                        try:
                            d_stop.quit()
                            logger.debug(f"Driver slot {idx_stop} ditutup karena stop")
                        except Exception as e:
                            logger.peringatan(f"Error saat menutup driver slot {idx_stop}: {str(e)}")
                        drivers[idx_stop] = None
                # Mark all as failed with stop message
                for idx_stop, file_path_stop in enumerate(chunk):
                    if chunk_results[idx_stop] is None:
                        chunk_results[idx_stop] = {
                            "file_path": file_path_stop,
                            "success": False,
                            "enhanced_path": None,
                            "error": "Dihentikan oleh user",
                            "start_time": start_times[idx_stop] if idx_stop < len(start_times) else datetime.now(),
                            "end_time": datetime.now(),
                            "duration": 0
                        }
                # Don't continue to next chunk
                break

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
                # Only count success/fail for the final pass or single pass mode
                is_final_pass = getattr(self, '_total_passes', 1) == 1 or getattr(self, '_current_pass', 1) == getattr(self, '_total_passes', 1)
                if is_final_pass:
                    if res.get("success"):
                        self.total_processed += 1
                    else:
                        self.total_failed += 1

            # ============================================================
            # AGGRESSIVE CLEANUP: Pastikan SEMUA Chrome ditutup sebelum batch berikutnya
            # ============================================================
            logger.info(f"=== Membersihkan {len(batch_driver_tracker)} Chrome dari batch {batch_num} ===")
            
            # Step 1: Close drivers from main array
            closed_count = 0
            for idx_d, d in enumerate(drivers):
                if d is not None:
                    try:
                        logger.debug(f"Menutup driver slot {idx_d}")
                        d.quit()
                        closed_count += 1
                    except Exception as e:
                        logger.peringatan(f"Error menutup driver slot {idx_d}", str(e))
                    drivers[idx_d] = None
            
            # Step 2: Force close ANY tracked driver that might have been missed
            for tracked_driver in batch_driver_tracker:
                if tracked_driver is not None:
                    try:
                        # Check if driver still alive
                        try:
                            _ = tracked_driver.current_url
                            # Still alive, force quit
                            tracked_driver.quit()
                            closed_count += 1
                            logger.debug("Menutup tracked driver yang masih hidup")
                        except Exception:
                            # Already dead, skip
                            pass
                    except Exception as e:
                        logger.peringatan(f"Error force closing tracked driver", str(e))
            
            for d in batch_driver_tracker:
                if d in self.global_driver_tracker:
                    self.global_driver_tracker.remove(d)
            batch_driver_tracker.clear()
            if closed_count > 0:
                logger.sukses(f"Batch {batch_num} cleanup selesai: {closed_count} Chrome ditutup")
            else:
                logger.info(f"Batch {batch_num} cleanup selesai: 0 Chrome ditutup (mungkin sudah tertutup atau gagal ditutup)")
            
            # Step 3: Wait for Chrome processes to fully terminate
            time.sleep(1)  # Give OS time to clean up processes
            
            # Cleanup any compressed temporary files
            for file_path in chunk:
                compressed_path = os.path.join(os.path.dirname(file_path), Path(file_path).stem + "_compressed.jpg")
                if os.path.exists(compressed_path):
                    try:
                        os.remove(compressed_path)
                        logger.debug(f"Menghapus file compressed: {os.path.basename(compressed_path)}")
                    except Exception as e:
                        logger.peringatan(f"Gagal menghapus compressed file", str(e))
            
            # Force garbage collection to free memory after each batch
            import gc
            gc.collect()
            logger.debug("Garbage collection selesai")
            
            # Brief pause before next batch to ensure clean state
            if start + batch_size < total_files:
                logger.debug("Menunggu sebentar sebelum batch berikutnya...")
                time.sleep(0.5)
        
        # Only set end_time and show final message if this is final pass or single pass
        current_pass = getattr(self, '_current_pass', 1)
        total_passes = getattr(self, '_total_passes', 1)
        
        if current_pass == total_passes:
            self.end_time = datetime.now()
            
            if self.file_update_signal:
                self.file_update_signal.file_update.emit("", True)
            
            upscale_info = f" ({self.upscale_level})" if self.upscale_level != "2x" else ""
            self.update_progress(
                f"Selesai{upscale_info}! Berhasil: {self.total_processed}, Gagal: {self.total_failed}",
                percentage=100
            )
            
            logger.sukses(
                f"Selesai memproses gambar{upscale_info}. Berhasil: {self.total_processed}, Gagal: {self.total_failed}",
                f"Durasi: {(self.end_time - self.start_time).total_seconds():.1f} detik"
            )
        else:
            pass_info = f"[Pass {current_pass}/{total_passes}]"
            logger.info(f"{pass_info} Selesai, melanjutkan ke pass berikutnya...")
    
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

                # Check file size and compress if needed (>10MB)
                upload_file_path = file_path
                compressed_file = None
                file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
                
                if file_size_mb > 10.0:
                    logger.info(f"File {file_name} terlalu besar ({file_size_mb:.2f}MB), mengompresi...")
                    try:
                        compressed_file = compress_image_to_limit(file_path, max_size_mb=9.5)  # 9.5MB to be safe
                        upload_file_path = compressed_file
                        logger.sukses(f"File berhasil dikompres untuk upload")
                    except Exception as comp_error:
                        logger.peringatan(f"Gagal mengompresi file, mencoba upload original: {str(comp_error)}")
                        upload_file_path = file_path

                input_file.send_keys(upload_file_path)
                time.sleep(self.polling_interval)
                
                # Check for file size error after upload
                try:
                    error_element = driver.find_element(By.CSS_SELECTOR, "span[data-testid='text'][class*='text-root']")
                    error_text = error_element.text if error_element else ""
                    
                    if "exceeds max size" in error_text.lower() or "10 mb" in error_text.lower():
                        logger.kesalahan(f"File {file_name} melebihi batas ukuran: {error_text}")
                        
                        # If we haven't tried compression yet, try now
                        if compressed_file is None and file_size_mb > 10.0:
                            logger.info("Mencoba dengan versi terkompres...")
                            compressed_file = compress_image_to_limit(file_path, max_size_mb=9.0)  # Even smaller
                            # Refresh page and retry
                            driver.refresh()
                            time.sleep(3)
                            
                            # Find input again
                            input_file = None
                            for selector in selectors_to_try:
                                try:
                                    input_file = driver.find_element(By.CSS_SELECTOR, selector)
                                    if input_file:
                                        break
                                except:
                                    continue
                            
                            if input_file:
                                input_file.send_keys(compressed_file)
                                time.sleep(self.polling_interval)
                                logger.sukses("Upload dengan file terkompres berhasil")
                            else:
                                raise Exception("Tidak dapat menemukan input setelah refresh")
                        else:
                            raise Exception(f"File terlalu besar bahkan setelah kompresi: {error_text}")
                except Exception as check_error:
                    # No error found or error checking failed, continue normally
                    if "exceeds max size" not in str(check_error).lower() and "terlalu besar" not in str(check_error).lower():
                        pass  # No size error, continue
                    else:
                        raise  # Re-raise size error

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
                        output_folder = self._get_output_folder(file_path)
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
                # Use original base name (without timestamp suffix) for consistent naming
                file_name = self._get_original_base_name(file_path)

                output_folder = self._get_output_folder(file_path)
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
            "upscale_level": self.upscale_level,
            "upscale_passes": self._get_upscale_passes(),
        }
        

        for result in self.results:
            if "file_path" in result:
                folder = os.path.dirname(result["file_path"])
                stats["processed_folders"].add(folder)
                
        stats["processed_folders"] = list(stats["processed_folders"])
        return stats