import os
import sys
import requests
import zipfile
import shutil

def download_chromedriver():
    # Get the base directory (where main.py is located)
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    
    # Define the download URL and paths
    CHROMEDRIVER_URL = "https://storage.googleapis.com/chrome-for-testing-public/138.0.7204.92/win64/chromedriver-win64.zip"
    DOWNLOAD_PATH = os.path.join(BASE_DIR, "chromedriver-win64.zip")
    DRIVER_DIR = os.path.join(BASE_DIR, "driver")
    EXTRACTION_DIR = os.path.join(BASE_DIR, "temp_extract")
    CHROMEDRIVER_PATH = os.path.join(DRIVER_DIR, "chromedriver.exe")
    
    print("SotongHD Driver Downloader")
    print("==========================")
    print(f"Base directory: {BASE_DIR}")
    
    # Create driver directory if it doesn't exist
    if not os.path.exists(DRIVER_DIR):
        print(f"Creating driver directory at {DRIVER_DIR}")
        os.makedirs(DRIVER_DIR, exist_ok=True)
    
    # Check if chromedriver already exists
    if os.path.exists(CHROMEDRIVER_PATH) and os.path.isfile(CHROMEDRIVER_PATH):
        print(f"ChromeDriver already exists at: {CHROMEDRIVER_PATH}")
        print("Skipping download.")
        return True
    
    print("ChromeDriver not found. Downloading...")
    
    try:
        # Download chromedriver zip file
        print(f"Downloading Chrome driver from: {CHROMEDRIVER_URL}")
        response = requests.get(CHROMEDRIVER_URL, stream=True)
        response.raise_for_status()
        
        # Save the zip file
        print(f"Saving to: {DOWNLOAD_PATH}")
        with open(DOWNLOAD_PATH, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        # Extract the zip file
        print("Extracting Chrome driver...")
        with zipfile.ZipFile(DOWNLOAD_PATH, 'r') as zip_ref:
            # Create temporary extraction directory
            if not os.path.exists(EXTRACTION_DIR):
                os.makedirs(EXTRACTION_DIR, exist_ok=True)
            zip_ref.extractall(EXTRACTION_DIR)
        
        # Move files from chromedriver-win64 subfolder to driver directory
        chromedriver_dir = os.path.join(EXTRACTION_DIR, "chromedriver-win64")
        for item in os.listdir(chromedriver_dir):
            source = os.path.join(chromedriver_dir, item)
            dest = os.path.join(DRIVER_DIR, item)
            
            if os.path.isfile(source):
                shutil.copy2(source, dest)
                print(f"Copied: {item} to driver directory")
            elif os.path.isdir(source):
                if os.path.exists(dest):
                    shutil.rmtree(dest)
                shutil.copytree(source, dest)
                print(f"Copied directory: {item} to driver directory")
        
        print("Cleaning up...")
        if os.path.exists(DOWNLOAD_PATH):
            os.remove(DOWNLOAD_PATH)
        if os.path.exists(EXTRACTION_DIR):
            shutil.rmtree(EXTRACTION_DIR)
        
        print("Chrome driver has been successfully downloaded and extracted to the driver directory.")
        return True
        
    except Exception as e:
        print(f"Error: {e}")
        return False

def set_app_icon(base_dir):
    """Find the icon file and set it for the application"""
    icon_path = os.path.join(base_dir, "App", "sotonghd.ico")
    if os.path.exists(icon_path) and os.path.isfile(icon_path):
        print(f"Using application icon: {icon_path}")
        return icon_path
    else:
        print("Warning: Application icon 'sotonghd.ico' not found.")
        return None

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
