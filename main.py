import os
import sys
import platform
import requests
import zipfile
import shutil
import re
import subprocess
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
from App.tools_checker import check_tools

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
    else:
        raise ValueError(f'Unsupported platform: {system} {machine}')



def set_app_icon(base_dir):
    icon_path = os.path.join(base_dir, "App", "sotonghd.ico")
    if os.path.exists(icon_path) and os.path.isfile(icon_path):
        return icon_path
    else:
        print("Warning: Application icon 'sotonghd.ico' not found.")
        return None

def get_chromedriver_link(platform_key: str):
    PAGE_URL = 'https://googlechromelabs.github.io/chrome-for-testing/'
    resp = requests.get(PAGE_URL, timeout=10)
    resp.raise_for_status()
    html = resp.text

    stable_start = html.find('id="stable"')
    if stable_start == -1:
        stable_start = html.find("id=stable")
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


def get_chromedriver_win64_link():
    return get_chromedriver_link('win64')


def main():
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    driver_filename = 'chromedriver.exe' if sys.platform == 'win32' else 'chromedriver'
    driver_path = os.path.join(BASE_DIR, 'driver', driver_filename)
    try:
        tools_ok = check_tools(BASE_DIR)
    except Exception as e:
        print(f"Error: Tools check failed: {e}")
        return 1
    if not tools_ok:
        print("Error: Tools check reported missing/failed tools; aborting startup.")
        return 1

    if sys.platform == "win32":
        try:
            import ctypes
            appid = u"mudrikam.SotongHD"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(appid)
        except Exception as e:
            print(f"Warning: Failed to set AppUserModelID: {e}")

    icon_path = set_app_icon(BASE_DIR)

    sys.path.insert(0, BASE_DIR)

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

