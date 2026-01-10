# SotongHD - Setup untuk Linux dan macOS

## Persyaratan Sistem

### macOS
1. **Google Chrome** harus terinstall
   ```bash
   # Install via Homebrew
   brew install --cask google-chrome
   
   # Atau download manual dari
   # https://www.google.com/chrome/
   ```

2. **Python 3.10+** (akan otomatis terinstall via Homebrew jika belum ada)

### Linux (Ubuntu/Debian)
1. **Google Chrome** harus terinstall
   ```bash
   # Download dan install Chrome
   wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
   sudo dpkg -i google-chrome-stable_current_amd64.deb
   sudo apt-get install -f
   
   # Atau via repository
   wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
   sudo sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list'
   sudo apt-get update
   sudo apt-get install google-chrome-stable
   ```

2. **Python 3.10+**
   ```bash
   sudo apt-get update
   sudo apt-get install python3 python3-pip python3-venv
   ```

### Linux (Fedora/RHEL/CentOS)
1. **Google Chrome**
   ```bash
   sudo dnf install google-chrome-stable
   ```

2. **Python 3.10+**
   ```bash
   sudo dnf install python3 python3-pip
   ```

## Cara Menjalankan

### Langkah 1: Beri Permission Execute pada Launcher
```bash
chmod +x Launcher.sh
```

### Langkah 2: Jalankan Aplikasi
```bash
./Launcher.sh
```

Script akan otomatis:
1. Mengecek/menginstall Python 3.10+ (via package manager sistem)
2. Membuat virtual environment di `python/macOS/venv` atau `python/Linux/venv`
3. Menginstall semua requirements dari `requirements.txt`
4. Mendownload ChromeDriver yang sesuai dengan platform Anda
5. Menjalankan aplikasi SotongHD

## Troubleshooting

### Error: "Chrome binary not found"
**Solusi:** Install Google Chrome terlebih dahulu (lihat instruksi di atas)

### Error: "Permission denied" saat jalankan Launcher.sh
**Solusi:**
```bash
chmod +x Launcher.sh
```

### Error: "chromedriver permission denied"
**Solusi:** Aplikasi akan otomatis set permission, tapi jika gagal:
```bash
chmod +x driver/chromedriver
```

### ChromeDriver tidak kompatibel dengan Chrome yang terinstall
**Solusi:** Hapus folder `driver/` dan jalankan ulang - akan auto-download versi terbaru:
```bash
rm -rf driver/
./Launcher.sh
```

### Virtual environment bermasalah
**Solusi:** Hapus dan buat ulang:
```bash
# macOS
rm -rf python/macOS/

# Linux
rm -rf python/Linux/

# Lalu jalankan ulang
./Launcher.sh
```

## Struktur Folder

```
SotongHD/
├── Launcher.sh              # Launcher untuk macOS/Linux
├── Launcher.bat             # Launcher untuk Windows
├── main.py                  # Script utama
├── requirements.txt         # Dependencies Python
├── config.json             # Konfigurasi aplikasi
├── driver/                 # ChromeDriver (auto-download)
│   └── chromedriver        # Binary ChromeDriver
├── python/                 # Python virtual environment
│   ├── macOS/             # Virtual env untuk macOS
│   │   └── venv/
│   └── Linux/             # Virtual env untuk Linux
│       └── venv/
└── App/                    # Source code aplikasi
    ├── sotonghd.py
    ├── background_process.py
    └── ...
```

## Catatan Penting

1. **ChromeDriver otomatis didownload** sesuai platform (win64, linux64, mac-x64, mac-arm64)
2. **Pastikan Chrome terinstall** sebelum menjalankan aplikasi
3. **Python 3.10+** diperlukan - script akan membantu install jika belum ada
4. **Internet connection** diperlukan untuk:
   - Download ChromeDriver pertama kali
   - Upload gambar ke Picsart
   - Update ChromeDriver

## Dukungan Platform

✅ Windows (x64, x86)
✅ macOS (Intel x64, Apple Silicon arm64)
✅ Linux (x64)

## Lisensi

MIT License - Copyright (c) 2025 Mudrikul Hikam, Desainia Studio
