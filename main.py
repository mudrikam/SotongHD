import os
import sys
import requests
import zipfile
import shutil
import re

def download_chromedriver():
    # Get the base directory (where main.py is located)
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    # Paths
    config_path = os.path.join(BASE_DIR, 'config.json')
    if not os.path.exists(config_path):
        raise FileNotFoundError(f'config.json not found at {config_path}')
    DOWNLOAD_PATH = os.path.join(BASE_DIR, "chromedriver-win64.zip")
    DRIVER_DIR = os.path.join(BASE_DIR, "driver")
    EXTRACTION_DIR = os.path.join(BASE_DIR, "temp_extract")
    CHROMEDRIVER_PATH = os.path.join(DRIVER_DIR, "chromedriver.exe")

    # Read local config URL
    import json
    with open(config_path, 'r', encoding='utf-8') as cf:
        cfg = json.load(cf)
    if 'chromedriver_url' not in cfg:
        raise ValueError('chromedriver_url missing in config.json')
    local_url = cfg['chromedriver_url']

    # Detect remote stable URL (may raise)
    remote_url = get_chromedriver_win64_link()

    sep = '-' * 40
    print(sep)
    print("SotongHD ChromeDriver Downloader")
    print(sep)
    print(f"Local chromedriver_url from config: {local_url}")
    print(f"Detected chromedriver_url from remote: {remote_url}")
    print(sep)

    # Helper: parse version like 140.0.7339.82 from the URL
    def extract_version_from_url(url: str) -> tuple:
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
    if cmp == 0:
        print('ChromeDriver is up to date')
        print(sep)
        return True

    print(sep)
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

    # Move files from chromedriver-win64 subfolder to driver directory
    chromedriver_dir = os.path.join(EXTRACTION_DIR, 'chromedriver-win64')
    if not os.path.exists(chromedriver_dir):
        # in some zips the files are at the root
        chromedriver_dir = EXTRACTION_DIR

    for item in os.listdir(chromedriver_dir):
        source = os.path.join(chromedriver_dir, item)
        dest = os.path.join(DRIVER_DIR, item)
        if os.path.isfile(source):
            shutil.copy2(source, dest)
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

def get_chromedriver_win64_link():
    """Fetch the chrome-for-testing page and extract the first chromedriver win64 URL.

    Returns the URL string or None if not found.
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

    # Search for the chromedriver win64 URL inside the stable section
    # Pattern matches the storage.googleapis.com path ending with /win64/chromedriver-win64.zip
    pattern = re.compile(r'https://storage\.googleapis\.com/[A-Za-z0-9_\-./]*/[0-9\.]+/win64/chromedriver-win64\.zip')
    m = pattern.search(stable_html)
    if not m:
        raise ValueError('chromedriver win64 URL not found in Stable section')
    return m.group(0)


def main():
    # Get the base directory
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    # Make sure chromedriver is downloaded
    download_chromedriver()

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

