import os
import sys
import platform
import json
import re
import subprocess
import shutil
import requests
import zipfile
import tempfile
import time

GREEN = '\x1b[32m'
RED = '\x1b[31m'
RESET = '\x1b[0m'

from App.ffmpeg_downloader import ensure_ffmpeg_present, is_ffmpeg_present


def get_platform_info():
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == 'windows':
        if machine in ('amd64', 'x86_64', 'x64'):
            return 'win64', 'chromedriver.exe', 'chromedriver-win64'
        else:
            return 'win32', 'chromedriver.exe', 'chromedriver-win32'
    elif system == 'darwin':
        if machine == 'arm64':
            return 'mac-arm64', 'chromedriver', 'chromedriver-mac-arm64'
        else:
            return 'mac-x64', 'chromedriver', 'chromedriver-mac-x64'
    elif system == 'linux':
        return 'linux64', 'chromedriver', 'chromedriver-linux64'
    raise ValueError(f'Unsupported platform: {system} {machine}')


def is_chromedriver_present(base_dir: str) -> bool:
    platform_key, driver_filename, _ = get_platform_info()
    driver_path = os.path.join(base_dir, 'driver', driver_filename)
    return os.path.isfile(driver_path)


def extract_version_from_url(url: str) -> tuple:
    if not url:
        return (0,)
    m = re.search(r'/([0-9]+(?:\.[0-9]+)*)/', url)
    if not m:
        print(f'Warning: Could not extract version from URL: {url}')
        return (0,)
    ver_str = m.group(1)
    return tuple(int(p) for p in ver_str.split('.'))


def version_cmp(a: tuple, b: tuple) -> int:
    la = len(a); lb = len(b)
    for i in range(max(la, lb)):
        ai = a[i] if i < la else 0
        bi = b[i] if i < lb else 0
        if ai < bi:
            return -1
        if ai > bi:
            return 1
    return 0


def get_local_chrome_version():
    candidates = []
    if sys.platform == 'win32':
        # Standard installation paths
        candidates.extend([
            os.path.join(os.environ.get('PROGRAMFILES', r'C:\Program Files'), 'Google', 'Chrome', 'Application', 'chrome.exe'),
            os.path.join(os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)'), 'Google', 'Chrome', 'Application', 'chrome.exe'),
            os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Google', 'Chrome', 'Application', 'chrome.exe'),
        ])
        
        # Try registry to find Chrome installation path
        try:
            import winreg
            reg_paths = [
                (winreg.HKEY_CURRENT_USER, r'Software\Google\Chrome\BLBeacon', 'version'),
                (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Google\Chrome\BLBeacon', 'version'),
                (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Google\Chrome\BLBeacon', 'version'),
            ]
            
            for hkey, path, value_name in reg_paths:
                try:
                    key = winreg.OpenKey(hkey, path)
                    version, _ = winreg.QueryValueEx(key, value_name)
                    winreg.CloseKey(key)
                    if version:
                        # Return version directly from registry
                        m = re.search(r'(\d+\.\d+\.\d+\.\d+)', version)
                        if m:
                            return tuple(int(x) for x in m.group(1).split('.'))
                except:
                    continue
                    
            # Try to get Chrome path from registry
            reg_exe_paths = [
                (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe', ''),
                (winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe', ''),
            ]
            
            for hkey, path, value_name in reg_exe_paths:
                try:
                    key = winreg.OpenKey(hkey, path)
                    chrome_path, _ = winreg.QueryValueEx(key, value_name)
                    winreg.CloseKey(key)
                    if chrome_path and os.path.exists(chrome_path):
                        candidates.insert(0, chrome_path)
                except:
                    continue
        except ImportError:
            pass
        except Exception as e:
            print(f'Registry check failed: {e}')
    
    # Check PATH
    chrome_on_path = shutil.which('chrome') or shutil.which('google-chrome') or shutil.which('chromium')
    if chrome_on_path:
        candidates.insert(0, chrome_on_path)
    
    # Try each candidate
    for exe in candidates:
        if exe and os.path.exists(exe):
            try:
                out = subprocess.check_output([exe, '--version'], stderr=subprocess.STDOUT, text=True, timeout=5)
            except Exception as e:
                print(f'Error checking local Chrome version from {exe}: {e}')
                continue
            m = re.search(r'(\d+\.\d+\.\d+\.\d+)', out)
            if m:
                print(f'Chrome detected at: {exe}')
                return tuple(int(x) for x in m.group(1).split('.'))
    return None


def get_local_chrome_version_string():
    """Get Chrome version as string (e.g., '144.0.7559.16')"""
    ver = get_local_chrome_version()
    if ver:
        return '.'.join(map(str, ver))
    return 'Not Found'


def get_chromedriver_version(base_dir: str):
    """Get ChromeDriver version from installed binary"""
    try:
        platform_key, driver_filename, _ = get_platform_info()
        driver_path = os.path.join(base_dir, 'driver', driver_filename)
        
        if not os.path.exists(driver_path):
            return 'Not Installed'
        
        try:
            out = subprocess.check_output([driver_path, '--version'], 
                                         stderr=subprocess.STDOUT, 
                                         text=True, 
                                         timeout=5)
            # Parse output like "ChromeDriver 145.0.7559.96 (...)"
            m = re.search(r'ChromeDriver\s+(\d+\.\d+\.\d+\.\d+)', out)
            if m:
                return m.group(1)
        except Exception as e:
            print(f'Error getting ChromeDriver version: {e}')
        
        return 'Unknown'
    except Exception:
        return 'Unknown'


def get_chromedriver_link(platform_key: str):
    PAGE_URL = 'https://googlechromelabs.github.io/chrome-for-testing/'
    resp = requests.get(PAGE_URL, timeout=10)
    resp.raise_for_status()
    html = resp.text
    stable_start = html.find('id="stable"')
    if stable_start == -1:
        stable_start = html.find('id=stable')
    if stable_start == -1:
        raise ValueError('Stable section not found on chrome-for-testing page')
    sec_open = html.rfind('<section', 0, stable_start)
    if sec_open == -1:
        raise ValueError('Stable section start tag not found')
    sec_close = html.find('</section>', stable_start)
    if sec_close == -1:
        raise ValueError('Stable section end tag not found')
    stable_html = html[sec_open:sec_close]
    pattern = re.compile(
        rf'https://storage\.googleapis\.com/[A-Za-z0-9_\-./]*/[0-9\.]+/{re.escape(platform_key)}/chromedriver-{re.escape(platform_key)}\.zip'
    )
    m = pattern.search(stable_html)
    if not m:
        raise ValueError(f'chromedriver {platform_key} URL not found in Stable section')
    return m.group(0)


def get_chromedriver_link_for_major(platform_key, major):
    """
    Get ChromeDriver download link for specific major version.
    Uses JSON API for more reliable version discovery.
    """
    try:
        # Try JSON API first (more reliable)
        api_url = "https://googlechromelabs.github.io/chrome-for-testing/known-good-versions-with-downloads.json"
        resp = requests.get(api_url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        # Find all versions matching the major version
        matching_versions = []
        for version_info in data.get('versions', []):
            version = version_info.get('version', '')
            if version.startswith(f'{major}.'):
                downloads = version_info.get('downloads', {})
                chromedriver_downloads = downloads.get('chromedriver', [])
                
                # Check if platform is available
                for dl in chromedriver_downloads:
                    if dl.get('platform') == platform_key:
                        matching_versions.append({
                            'version': version,
                            'url': dl.get('url')
                        })
                        break
        
        if matching_versions:
            # Return the latest version
            latest = matching_versions[-1]
            print(f"Found ChromeDriver {latest['version']} for Chrome {major} via JSON API")
            return latest['url']
        
        print(f"No ChromeDriver found for major version {major} in JSON API")
        return None
        
    except Exception as e:
        print(f"JSON API failed ({e}), trying HTML page method...")
        
        # Fallback to HTML page method
        try:
            PAGE_URL = 'https://googlechromelabs.github.io/chrome-for-testing/'
            resp_major = requests.get(PAGE_URL, timeout=10)
            resp_major.raise_for_status()
            html_major = resp_major.text
            pattern_major = re.compile(
                rf'https://storage\.googleapis\.com/[A-Za-z0-9_\-./]*/{major}\.[0-9\.]*?/{re.escape(platform_key)}/chromedriver-{re.escape(platform_key)}\.zip'
            )
            m_major = pattern_major.search(html_major)
            if m_major:
                return m_major.group(0)
        except Exception as e2:
            print(f"HTML page method also failed: {e2}")
        
        return None


def download_chromedriver_for_chrome_version(base_dir: str, force_major_version: int = None) -> bool:
    """
    Download ChromeDriver that matches the installed Chrome version.
    If exact version not found, tries progressively older versions.
    
    Args:
        base_dir: Base directory of the application
        force_major_version: If provided, download for this specific major version
        
    Returns:
        True if successful, False otherwise
    """
    try:
        platform_key, driver_filename, zip_folder_name = get_platform_info()
        
        # Get Chrome version
        chrome_version = get_local_chrome_version()
        if not chrome_version:
            print('Warning: Could not detect local Chrome version')
            if not force_major_version:
                return False
            major_version = force_major_version
        else:
            major_version = force_major_version if force_major_version else chrome_version[0]
        
        print(f'Target Chrome major version: {major_version}')
        
        # Try to find compatible ChromeDriver version
        driver_url = None
        attempted_versions = []
        
        # Try exact match first
        print(f'Attempting to download ChromeDriver for Chrome major version {major_version}')
        driver_url = get_chromedriver_link_for_major(platform_key, major_version)
        attempted_versions.append(major_version)
        
        # If not found, try older versions (up to 5 versions back)
        if not driver_url:
            print(f'No ChromeDriver found for Chrome major version {major_version}')
            print('Trying older ChromeDriver versions (progressive fallback)...')
            
            for offset in range(1, 6):  # Try 5 versions back
                fallback_version = major_version - offset
                if fallback_version < 100:  # Don't go too far back
                    break
                
                print(f'  Trying ChromeDriver v{fallback_version}...')
                driver_url = get_chromedriver_link_for_major(platform_key, fallback_version)
                attempted_versions.append(fallback_version)
                
                if driver_url:
                    print(f'  ✓ Found ChromeDriver v{fallback_version} (compatible with Chrome {major_version})')
                    break
        
        if not driver_url:
            print(f'Warning: No compatible ChromeDriver found for Chrome {major_version}')
            print(f'Attempted versions: {attempted_versions}')
            # Try the stable version as last resort
            print('Falling back to latest stable ChromeDriver version')
            driver_url = get_chromedriver_link(platform_key)
            if not driver_url:
                print('Error: Could not find any ChromeDriver download URL')
                return False
            print('Warning: Using latest stable may cause version mismatch')
        
        print(f'Found ChromeDriver URL: {driver_url}')
        
        # Download and install
        DOWNLOAD_PATH = os.path.join(base_dir, f"chromedriver-{platform_key}.zip")
        DRIVER_DIR = os.path.join(base_dir, "driver")
        EXTRACTION_DIR = os.path.join(base_dir, "temp_extract")
        CHROMEDRIVER_PATH = os.path.join(DRIVER_DIR, driver_filename)
        
        # Backup existing driver if it exists
        backup_path = None
        if os.path.exists(CHROMEDRIVER_PATH):
            backup_path = CHROMEDRIVER_PATH + '.backup'
            print(f'Backing up existing ChromeDriver to {backup_path}')
            shutil.copy2(CHROMEDRIVER_PATH, backup_path)
        
        try:
            # Download
            print(f'Downloading ChromeDriver from: {driver_url}')
            resp = requests.get(driver_url, stream=True, timeout=60)
            resp.raise_for_status()
            
            with open(DOWNLOAD_PATH, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            print('ChromeDriver downloaded successfully')
            
            # Extract
            print('Extracting ChromeDriver...')
            if not zipfile.is_zipfile(DOWNLOAD_PATH):
                raise ValueError('Downloaded ChromeDriver is not a valid zip archive')
            
            # Remove old driver directory
            if os.path.exists(DRIVER_DIR):
                shutil.rmtree(DRIVER_DIR)
            os.makedirs(DRIVER_DIR, exist_ok=True)
            
            with zipfile.ZipFile(DOWNLOAD_PATH, 'r') as zip_ref:
                os.makedirs(EXTRACTION_DIR, exist_ok=True)
                zip_ref.extractall(EXTRACTION_DIR)
            
            # Find and copy chromedriver
            chromedriver_dir = os.path.join(EXTRACTION_DIR, zip_folder_name)
            if not os.path.exists(chromedriver_dir):
                chromedriver_dir = EXTRACTION_DIR
            
            for item in os.listdir(chromedriver_dir):
                source = os.path.join(chromedriver_dir, item)
                dest = os.path.join(DRIVER_DIR, item)
                if os.path.isfile(source):
                    shutil.copy2(source, dest)
                    if sys.platform != 'win32' and item == driver_filename:
                        os.chmod(dest, 0o755)
                    print(f'Copied: {item} to driver directory')
                elif os.path.isdir(source):
                    if os.path.exists(dest):
                        shutil.rmtree(dest)
                    shutil.copytree(source, dest)
                    print(f'Copied directory: {item} to driver directory')
            
            # Cleanup
            if os.path.exists(DOWNLOAD_PATH):
                os.remove(DOWNLOAD_PATH)
            if os.path.exists(EXTRACTION_DIR):
                shutil.rmtree(EXTRACTION_DIR)
            
            # Update config
            config_path = os.path.join(base_dir, 'config.json')
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as cf:
                    cfg = json.load(cf)
                
                config_url_key = f'chromedriver_url_{platform_key}'
                if config_url_key not in cfg and platform_key == 'win64' and 'chromedriver_url' in cfg:
                    config_url_key = 'chromedriver_url'
                
                cfg[config_url_key] = driver_url
                
                with open(config_path, 'w', encoding='utf-8') as cf:
                    json.dump(cfg, cf, indent=2)
                
                print('config.json updated with new chromedriver_url')
            
            # Remove backup if successful
            if backup_path and os.path.exists(backup_path):
                os.remove(backup_path)
            
            print(f'ChromeDriver for Chrome {major_version} installed successfully')
            return True
            
        except Exception as e:
            print(f'Error during ChromeDriver download/installation: {e}')
            # Restore backup if available
            if backup_path and os.path.exists(backup_path):
                print('Restoring backup ChromeDriver')
                os.makedirs(DRIVER_DIR, exist_ok=True)
                shutil.copy2(backup_path, CHROMEDRIVER_PATH)
                os.remove(backup_path)
            raise
            
    except Exception as e:
        print(f'Failed to download ChromeDriver for Chrome version: {e}')
        return False


def ensure_chromedriver_present(base_dir: str) -> bool:
    platform_key, driver_filename, zip_folder_name = get_platform_info()
    config_path = os.path.join(base_dir, 'config.json')
    if not os.path.exists(config_path):
        raise FileNotFoundError(f'config.json not found at {config_path}')
    DOWNLOAD_PATH = os.path.join(base_dir, f"chromedriver-{platform_key}.zip")
    DRIVER_DIR = os.path.join(base_dir, "driver")
    EXTRACTION_DIR = os.path.join(base_dir, "temp_extract")
    CHROMEDRIVER_PATH = os.path.join(DRIVER_DIR, driver_filename)
    with open(config_path, 'r', encoding='utf-8') as cf:
        cfg = json.load(cf)
    config_url_key = f'chromedriver_url_{platform_key}'
    if config_url_key not in cfg and platform_key == 'win64' and 'chromedriver_url' in cfg:
        config_url_key = 'chromedriver_url'
    local_url = cfg.get(config_url_key, '')
    
    # Try to match local Chrome version first
    local_chrome_ver = get_local_chrome_version()
    if local_chrome_ver:
        local_major = local_chrome_ver[0]
        ver_str = '.'.join(map(str, local_chrome_ver))
        print(f'Detected local Chrome version: {ver_str} (major: {local_major})')
        alt_url = get_chromedriver_link_for_major(platform_key, local_major)
        if alt_url:
            print(f'Using ChromeDriver matching local Chrome major version: {local_major}')
            remote_url = alt_url
            download_url = alt_url
        else:
            print(f'No ChromeDriver found for local Chrome major {local_major}; trying stable version')
            remote_url = get_chromedriver_link(platform_key)
            download_url = remote_url
    elif local_url:
        remote_url = None
        download_url = local_url
    else:
        remote_url = get_chromedriver_link(platform_key)
        download_url = remote_url
    sep = '-' * 40
    print(sep)
    print(f"SotongHD ChromeDriver Downloader ({platform_key})")
    print(sep)
    print(f"Platform: {platform.system()} {platform.machine()}")
    print(f"Local {config_url_key} from config: {local_url or '(not set)'}")
    print(f"Detected chromedriver_url from remote: {remote_url}")
    print(sep)
    local_ver = extract_version_from_url(local_url)
    remote_ver = extract_version_from_url(remote_url) if remote_url else (0,)
    cmp = version_cmp(local_ver, remote_ver)
    if cmp == 0 and os.path.exists(CHROMEDRIVER_PATH):
        print('ChromeDriver is up to date')
        print(sep)
        return True
    print(sep)
    if not os.path.exists(CHROMEDRIVER_PATH):
        print('ChromeDriver not found; downloading...')
    else:
        print('ChromeDriver is outdated; updating to remote version')
    print(sep)
    if os.path.exists(DRIVER_DIR):
        print(f'Removing existing driver directory: {DRIVER_DIR}')
        shutil.rmtree(DRIVER_DIR)
    os.makedirs(DRIVER_DIR, exist_ok=True)
    print(f'Downloading Chrome driver from: {download_url}')
    head = requests.head(download_url, allow_redirects=True, timeout=20)
    head.raise_for_status()
    total = head.headers.get('Content-Length')
    if total is None:
        size_mb = cfg.get('chromedriver_size_mb')
        size_bytes = cfg.get('chromedriver_size')
        if size_bytes:
            total = int(size_bytes)
        elif size_mb:
            total = int(float(size_mb) * 1024 * 1024)
        else:
            raise ValueError('Content-Length not provided for chromedriver URL and chromedriver_size/chromedriver_size_mb not set in config.json; cannot show deterministic progress bar')
    else:
        total = int(total)
    resp = requests.get(download_url, stream=True)
    resp.raise_for_status()
    with open(DOWNLOAD_PATH, 'wb') as f:
        downloaded = 0
        bar_width = 25
        start_time = time.time()
        last_update = start_time
        update_interval = 0.25
        last_percent = -1
        for chunk in resp.iter_content(chunk_size=8192):
            if not chunk:
                continue
            f.write(chunk)
            downloaded += len(chunk)
            now = time.time()
            elapsed = max(0.001, now - start_time)
            mb_dl = downloaded / 1024 / 1024
            speed = mb_dl / elapsed
            percent = int(downloaded * 100 / total)
            if percent != last_percent or (now - last_update) >= update_interval:
                last_percent = percent
                last_update = now
                filled = int(bar_width * percent / 100)
                bar = '+' * filled + '-' * (bar_width - filled)
                colored_bar = ''.join((GREEN + c + RESET) if c == '+' else (RED + c + RESET) for c in bar)
                human_dl = f'{mb_dl:.2f}MB'
                human_total = f'{total/1024/1024:.2f}MB'
                eta = (total - downloaded) / (downloaded / elapsed) if downloaded > 0 else 0
                eta_str = f'{int(eta)}s' if eta >= 1 else '<1s'
                print(f'\rDownloading ChromeDriver [{colored_bar}] {percent}% {human_dl}/{human_total} {speed:.2f}MB/s ETA {eta_str}', end='', flush=True)
    colored_filled = ''.join((GREEN + c + RESET) if c == '+' else (RED + c + RESET) for c in ('+' * bar_width))
    human_total = f'{total/1024/1024:.2f}MB'
    print(f'\rDownloading ChromeDriver [{colored_filled}] 100% {human_total}/{human_total} {speed:.2f}MB/s')

    print('Extracting Chrome driver...')
    if not zipfile.is_zipfile(DOWNLOAD_PATH):
        raise ValueError('Downloaded ChromeDriver is not a valid zip archive')
    with zipfile.ZipFile(DOWNLOAD_PATH, 'r') as zip_ref:
        os.makedirs(EXTRACTION_DIR, exist_ok=True)
        zip_ref.extractall(EXTRACTION_DIR)
    if not os.path.exists(EXTRACTION_DIR):
        raise FileNotFoundError(f'Extraction directory not found after extraction: {EXTRACTION_DIR}')

    chromedriver_dir = os.path.join(EXTRACTION_DIR, zip_folder_name)
    if not os.path.exists(chromedriver_dir):
        chromedriver_dir = EXTRACTION_DIR
    if not os.path.exists(chromedriver_dir):
        raise FileNotFoundError(f'Chromedriver extraction directory not found: {chromedriver_dir}')

    for item in os.listdir(chromedriver_dir):
        source = os.path.join(chromedriver_dir, item)
        dest = os.path.join(DRIVER_DIR, item)
        if os.path.isfile(source):
            shutil.copy2(source, dest)
            if sys.platform != 'win32' and item == driver_filename:
                os.chmod(dest, 0o755)
            print(f'Copied: {item} to driver directory')
        elif os.path.isdir(source):
            if os.path.exists(dest):
                shutil.rmtree(dest)
            shutil.copytree(source, dest)
            print(f'Copied directory: {item} to driver directory')
    if os.path.exists(DOWNLOAD_PATH):
        os.remove(DOWNLOAD_PATH)
    if os.path.exists(EXTRACTION_DIR):
        shutil.rmtree(EXTRACTION_DIR)
    cfg[config_url_key] = download_url
    with open(config_path, 'w', encoding='utf-8') as cf:
        json.dump(cfg, cf, indent=2)
    print(sep)
    print('config.json updated with new chromedriver_url')
    print('Chrome driver has been successfully updated and extracted to the driver directory.')
    print(sep)
    return True


def check_tools(base_dir: str) -> bool:
    sep = '-' * 40
    print(sep)
    print('SotongHD Tools Checker')
    print(sep)
    chromedriver_ok = False
    ffmpeg_ok = False
    try:
        chromedriver_ok = is_chromedriver_present(base_dir)
        if not chromedriver_ok:
            ensure_chromedriver_present(base_dir)
            chromedriver_ok = is_chromedriver_present(base_dir)
    except Exception as e:
        print(f'Error while ensuring ChromeDriver: {e}')
        raise
    try:
        ffmpeg_ok = is_ffmpeg_present(base_dir)
        if not ffmpeg_ok:
            ensure_ffmpeg_present(base_dir)
            ffmpeg_ok = is_ffmpeg_present(base_dir)
    except Exception as e:
        print(f'Error while ensuring ffmpeg: {e}')
        raise
    print(sep)
    print(f'ChromeDriver present: {chromedriver_ok}')
    print(f'ffmpeg present: {ffmpeg_ok}')
    print(sep)
    return chromedriver_ok and ffmpeg_ok
