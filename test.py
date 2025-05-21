from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import requests
import os
from datetime import datetime

# Lokasi file gambar yang akan diupload
file_path = r"C:\Users\mudri\Downloads\unnamed (1).png"

# Lokasi ChromeDriver
chromedriver_path = r"Z:\Build\chromedriver.exe"

# Konfigurasi browser untuk headless mode
chrome_options = Options()
chrome_options.add_argument("--headless=new")  # Mode headless baru untuk Chrome
chrome_options.add_argument("--disable-gpu")  # Diperlukan untuk Windows
chrome_options.add_argument("--window-size=1920,1080")  # Set ukuran window virtual
chrome_options.add_argument("--log-level=3")  # Suppress console messages
chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])

# Inisialisasi Chrome dengan lokasi driver
driver = webdriver.Chrome(service=Service(chromedriver_path), options=chrome_options)

try:
    # Buka halaman Picsart AI Image Enhancer
    print("⏳ Membuka browser dalam background mode...")
    driver.get("https://picsart.com/id/ai-image-enhancer/")
    time.sleep(5)  # Tunggu halaman dan elemen render

    # Cari elemen input type="file" (biasanya disembunyikan oleh CSS)
    input_file = driver.find_element(By.XPATH, "//input[@type='file']")
    
    # Upload file ke elemen input
    input_file.send_keys(file_path)

    print("✅ File berhasil dikirim.")
    
    # Tunggu sampai element dengan data-testid="EnhancedImage" muncul
    print("⏳ Menunggu proses enhancement selesai...")
    
    # Implementasi retry logic dengan timeout keseluruhan
    max_wait_time = 300  # 5 menit total
    polling_interval = 5  # cek setiap 5 detik
    start_time = time.time()
    
    found_image = False
    
    while time.time() - start_time < max_wait_time and not found_image:
        try:
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
                                print(f"✅ Image ditemukan dengan selector: {selector}")
                                found_image = True
                                break
                        
                        if found_image:
                            break
                except Exception as e:
                    print(f"Info: Selector {selector} tidak berhasil: {e}")
                    continue
            
            if not found_image:
                print(f"Masih memproses... ({int(time.time() - start_time)} detik berlalu)")
                time.sleep(polling_interval)
        except Exception as e:
            print(f"Pengecualian saat mencari gambar: {e}")
            time.sleep(polling_interval)
    
    if not found_image:
        print("❌ Tidak dapat menemukan gambar hasil enhancement dalam batas waktu.")
        # Ambil screenshot sebagai bukti
        driver.save_screenshot(os.path.join(r"Z:\Build\test picsart\downloads", f"error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"))
        raise Exception("Tidak dapat menemukan gambar hasil enhancement")
    
    print(f"✅ Image ditemukan: {image_url}")
    
    # Download image
    response = requests.get(image_url, stream=True)
    if response.status_code == 200:
        # Buat nama file dengan timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        download_folder = r"Z:\Build\test picsart\downloads"
        
        # Pastikan folder ada
        os.makedirs(download_folder, exist_ok=True)
        
        # Simpan file
        file_name = os.path.join(download_folder, f"enhanced_image_{timestamp}.png")
        with open(file_name, 'wb') as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)
        
        print(f"✅ Image berhasil diunduh: {file_name}")
    else:
        print(f"❌ Gagal mengunduh image. Status code: {response.status_code}")

    print("Proses selesai! Browser akan ditutup dalam 5 detik...")
    time.sleep(5)
finally:
    driver.quit()
