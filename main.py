import os
import sys
import platform
import requests
import zipfile
import shutil
import re
import subprocess

def get_platform_info():
    """Detect current platform and return platform key and driver filename.
    
    Returns:
        tuple: (platform_key, driver_filename, zip_folder_name)
            - platform_key: 'win64', 'win32', 'linux64', 'mac-x64', 'mac-arm64'
            - driver_filename: 'chromedriver.exe' for Windows, 'chromedriver' for others
            - zip_folder_name: folder name inside the zip file
    """
    system = platform.system().lower()
    machine = platform.machine().lower()
    
    if system == 'windows':
        if machine in ('amd64', 'x86_64', 'x64'):
            return 'win64', 'chromedriver.exe', 'chromedriver-win64'
        else:
            return 'win32', 'chromedriver.exe', 'chromedriver-win32'
    elif system == 'darwin':  # macOS
        if machine == 'arm64':
            return 'mac-arm64', 'chromedriver', 'chromedriver-mac-arm64'
        else:
            return 'mac-x64', 'chromedriver', 'chromedriver-mac-x64'
    elif system == 'linux':
        return 'linux64', 'chromedriver', 'chromedriver-linux64'
    else:
        raise ValueError(f'Unsupported platform: {system} {machine}')

def download_chromedriver():
    # Get the base directory (where main.py is located)
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    # Detect platform
    platform_key, driver_filename, zip_folder_name = get_platform_info()
    
    # Paths
    config_path = os.path.join(BASE_DIR, 'config.json')
    if not os.path.exists(config_path):
        raise FileNotFoundError(f'config.json not found at {config_path}')
    DOWNLOAD_PATH = os.path.join(BASE_DIR, f"chromedriver-{platform_key}.zip")
    DRIVER_DIR = os.path.join(BASE_DIR, "driver")
    EXTRACTION_DIR = os.path.join(BASE_DIR, "temp_extract")
    CHROMEDRIVER_PATH = os.path.join(DRIVER_DIR, driver_filename)

    # Read local config URL
    import json
    with open(config_path, 'r', encoding='utf-8') as cf:
        cfg = json.load(cf)
    
    # Config key for this platform's chromedriver URL
    config_url_key = f'chromedriver_url_{platform_key}'
    # Fallback to old key for backward compatibility (win64)
    if config_url_key not in cfg and platform_key == 'win64' and 'chromedriver_url' in cfg:
        config_url_key = 'chromedriver_url'
    
    local_url = cfg.get(config_url_key, '')

    # Detect remote stable URL (may raise)
    remote_url = get_chromedriver_link(platform_key)

    # Attempt to detect local Chrome version and prefer matching ChromeDriver major version
    def get_local_chrome_version():
        """Return tuple version (major, minor, build, patch) or None if detection fails"""
        try:
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
                        m = re.search(r'(\d+\.\d+\.\d+\.\d+)', out)
                        if m:
                            return tuple(int(x) for x in m.group(1).split('.'))
                    except Exception:
                        continue
        except Exception:
            pass
        return None

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
    print(f"Local chromedriver_url from config: {local_url or '(not set)'}")
    print(f"Detected chromedriver_url from remote: {remote_url}")
    print(sep)

    # Helper: parse version like 140.0.7339.82 from the URL
    def extract_version_from_url(url: str) -> tuple:
        if not url:
            return (0,)
        m = re.search(r'/([0-9]+(?:\.[0-9]+)*)/', url)
        if not m:
            raise ValueError(f'Could not extract version from URL: {url}')
        ver_str = m.group(1)
        return tuple(int(p) for p in ver_str.split('.'))

    local_ver = extract_version_from_url(local_url)
    remote_ver = extract_version_from_url(remote_url)

    def version_cmp(a: tuple, b: tuple) -> int:
        # return -1 if a<b, 0 if equal, 1 if a>b
        la = len(a); lb = len(b)
        for i in range(max(la, lb)):
            ai = a[i] if i < la else 0
            bi = b[i] if i < lb else 0
            if ai < bi:
                return -1
            if ai > bi:
                return 1
        return 0

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

    # Remove existing driver files if any
    if os.path.exists(DRIVER_DIR):
        print(f'Removing existing driver directory: {DRIVER_DIR}')
        shutil.rmtree(DRIVER_DIR)
    os.makedirs(DRIVER_DIR, exist_ok=True)

    # Download remote zip
    print(f'Downloading Chrome driver from: {remote_url}')
    resp = requests.get(remote_url, stream=True)
    resp.raise_for_status()
    with open(DOWNLOAD_PATH, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)

    # Extract
    print('Extracting Chrome driver...')
    with zipfile.ZipFile(DOWNLOAD_PATH, 'r') as zip_ref:
        if not os.path.exists(EXTRACTION_DIR):
            os.makedirs(EXTRACTION_DIR, exist_ok=True)
        zip_ref.extractall(EXTRACTION_DIR)

    # Move files from chromedriver subfolder to driver directory
    chromedriver_dir = os.path.join(EXTRACTION_DIR, zip_folder_name)
    if not os.path.exists(chromedriver_dir):
        # in some zips the files are at the root
        chromedriver_dir = EXTRACTION_DIR

    for item in os.listdir(chromedriver_dir):
        source = os.path.join(chromedriver_dir, item)
        dest = os.path.join(DRIVER_DIR, item)
        if os.path.isfile(source):
            shutil.copy2(source, dest)
            # Make executable on Unix-like systems
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

    # Update config.json to the new remote URL
    cfg[config_url_key] = remote_url
    # Also update the legacy key for win64 compatibility
    if platform_key == 'win64':
        cfg['chromedriver_url'] = remote_url
    with open(config_path, 'w', encoding='utf-8') as cf:
        json.dump(cfg, cf, indent=2)
    print(sep)
    print('config.json updated with new chromedriver_url')
    print('Chrome driver has been successfully updated and extracted to the driver directory.')
    print(sep)
    return True

def set_app_icon(base_dir):
    """Find the icon file and set it for the application"""
    icon_path = os.path.join(base_dir, "App", "sotonghd.ico")
    if os.path.exists(icon_path) and os.path.isfile(icon_path):
        return icon_path
    else:
        print("Warning: Application icon 'sotonghd.ico' not found.")
        return None

def get_chromedriver_link(platform_key: str):
    """Fetch the chrome-for-testing page and extract the chromedriver URL for the given platform.

    Args:
        platform_key: One of 'win64', 'win32', 'linux64', 'mac-x64', 'mac-arm64'
        
    Returns the URL string or raises ValueError if not found.
    """
    PAGE_URL = 'https://googlechromelabs.github.io/chrome-for-testing/'
    resp = requests.get(PAGE_URL, timeout=10)
    resp.raise_for_status()
    html = resp.text

    # Find the <section ... id="stable"> ... </section> block
    stable_start = html.find('id="stable"')
    if stable_start == -1:
        # try without quotes (some HTML may omit them)
        stable_start = html.find("id=stable")
    if stable_start == -1:
        raise ValueError('Stable section not found on chrome-for-testing page')

    # Find the start of the <section tag containing the stable id
    sec_open = html.rfind('<section', 0, stable_start)
    if sec_open == -1:
        raise ValueError('Stable section start tag not found')

    sec_close = html.find('</section>', stable_start)
    if sec_close == -1:
        raise ValueError('Stable section end tag not found')

    stable_html = html[sec_open:sec_close]

    # Search for the chromedriver URL for the specified platform inside the stable section
    # Pattern matches the storage.googleapis.com path ending with /{platform}/chromedriver-{platform}.zip
    pattern = re.compile(
        rf'https://storage\.googleapis\.com/[A-Za-z0-9_\-./]*/[0-9\.]+/{re.escape(platform_key)}/chromedriver-{re.escape(platform_key)}\.zip'
    )
    m = pattern.search(stable_html)
    if not m:
        raise ValueError(f'chromedriver {platform_key} URL not found in Stable section')
    return m.group(0)


# Keep backward compatibility alias
def get_chromedriver_win64_link():
    """Backward compatibility wrapper for get_chromedriver_link('win64')"""
    return get_chromedriver_link('win64')


def main():
    # Get the base directory
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    # Make sure chromedriver is downloaded
    download_chromedriver()

    # Set Windows AppUserModelID for proper taskbar icon (only on Windows)
    if sys.platform == "win32":
        try:
            import ctypes
            appid = u"mudrikam.SotongHD"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(appid)
        except Exception as e:
            print(f"Warning: Failed to set AppUserModelID: {e}")

    # Get the icon path
    icon_path = set_app_icon(BASE_DIR)

    # Add the app directory to the Python path so we can import from it
    sys.path.insert(0, BASE_DIR)

    # Import and run the SotongHD application
    try:
        from App.sotonghd import run_app
        print("Starting SotongHD application...")
        run_app(BASE_DIR, icon_path)
    except ImportError as e:
        print(f"Error importing SotongHD application: {e}")
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())

