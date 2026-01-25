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
        raise ValueError(f'Could not extract version from URL: {url}')
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
        candidates.extend([
            os.path.join(os.environ.get('PROGRAMFILES', r'C:\Program Files'), 'Google', 'Chrome', 'Application', 'chrome.exe'),
            os.path.join(os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)'), 'Google', 'Chrome', 'Application', 'chrome.exe'),
        ])
    chrome_on_path = shutil.which('chrome') or shutil.which('google-chrome') or shutil.which('chromium')
    if chrome_on_path:
        candidates.append(chrome_on_path)
    for exe in candidates:
        if exe and os.path.exists(exe):
            try:
                out = subprocess.check_output([exe, '--version'], stderr=subprocess.STDOUT, text=True, timeout=5)
            except Exception as e:
                print(f'Error checking local Chrome version from {exe}: {e}')
                continue
            m = re.search(r'(\d+\.\d+\.\d+\.\d+)', out)
            if m:
                return tuple(int(x) for x in m.group(1).split('.'))
    return None


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
    return None


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
    local_url = cfg.get(config_url_key, '')
    remote_url = get_chromedriver_link(platform_key)
    local_chrome_ver = get_local_chrome_version()
    if local_chrome_ver:
        local_major = local_chrome_ver[0]
        alt_url = get_chromedriver_link_for_major(platform_key, local_major)
        if alt_url:
            print(f'Using ChromeDriver matching local Chrome major version: {local_major}')
            remote_url = alt_url
        else:
            print(f'No ChromeDriver found for local Chrome major {local_major}; defaulting to stable remote URL')
    sep = '-' * 40
    print(sep)
    print(f"SotongHD ChromeDriver Downloader ({platform_key})")
    print(sep)
    print(f"Platform: {platform.system()} {platform.machine()}")
    print(f"Local {config_url_key} from config: {local_url or '(not set)'}")
    print(f"Detected chromedriver_url from remote: {remote_url}")
    print(sep)
    local_ver = extract_version_from_url(local_url)
    remote_ver = extract_version_from_url(remote_url)
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
    print(f'Downloading Chrome driver from: {remote_url}')
    resp = requests.get(remote_url, stream=True)
    resp.raise_for_status()
    with open(DOWNLOAD_PATH, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    with zipfile.ZipFile(DOWNLOAD_PATH, 'r') as zip_ref:
        if not os.path.exists(EXTRACTION_DIR):
            os.makedirs(EXTRACTION_DIR, exist_ok=True)
        zip_ref.extractall(EXTRACTION_DIR)
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
    if os.path.exists(DOWNLOAD_PATH):
        os.remove(DOWNLOAD_PATH)
    if os.path.exists(EXTRACTION_DIR):
        shutil.rmtree(EXTRACTION_DIR)
    cfg[config_url_key] = remote_url
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
