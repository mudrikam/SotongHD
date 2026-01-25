import os
import sys
import json
import shutil
import requests
import zipfile
import tarfile
import tempfile
import time
GREEN = '\x1b[32m'
RED = '\x1b[31m'
RESET = '\x1b[0m'


def is_ffmpeg_present(base_dir: str) -> bool:
    ffmpeg_dir = os.path.join(base_dir, 'ffmpeg')
    if not os.path.isdir(ffmpeg_dir):
        return False
    exe = 'ffmpeg.exe' if sys.platform == 'win32' else 'ffmpeg'
    return os.path.isfile(os.path.join(ffmpeg_dir, exe))


def ensure_ffmpeg_present(base_dir: str) -> bool:
    if is_ffmpeg_present(base_dir):
        print('ffmpeg is present')
        return True
    download_and_extract_ffmpeg(base_dir)
    if not is_ffmpeg_present(base_dir):
        raise RuntimeError('ffmpeg installation failed: executable not found after extraction')
    return True


def download_and_extract_ffmpeg(base_dir: str) -> None:
    config_path = os.path.join(base_dir, 'config.json')
    if not os.path.exists(config_path):
        raise FileNotFoundError(f'config.json not found at {config_path}')
    with open(config_path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    ffmpeg_url = cfg.get('ffmpeg_url', '').strip()
    if not ffmpeg_url:
        raise ValueError('ffmpeg_url is not set in config.json')
    sep = '-' * 40
    print(sep)
    print('SotongHD ffmpeg Downloader')
    print(sep)
    print(f'Downloading ffmpeg from: {ffmpeg_url}')
    head = requests.head(ffmpeg_url, allow_redirects=True, timeout=20)
    head.raise_for_status()
    total = head.headers.get('Content-Length')
    if total is None:
        size_mb = cfg.get('ffmpeg_size_mb')
        size_bytes = cfg.get('ffmpeg_size')
        if size_bytes:
            total = int(size_bytes)
        elif size_mb:
            total = int(float(size_mb) * 1024 * 1024)
        else:
            raise ValueError('Content-Length not provided for ffmpeg_url and ffmpeg_size/ffmpeg_size_mb not set in config.json; cannot show deterministic progress bar')
    else:
        total = int(total)
    resp = requests.get(ffmpeg_url, stream=True, timeout=60)
    resp.raise_for_status()
    tmp_fd, tmp_path = tempfile.mkstemp(suffix='_ffmpeg_download')
    os.close(tmp_fd)
    bar_width = 25
    start_time = time.time()
    last_update = start_time
    update_interval = 0.25
    with open(tmp_path, 'wb') as out:
        downloaded = 0
        last_percent = -1
        for chunk in resp.iter_content(chunk_size=8192):
            if not chunk:
                continue
            out.write(chunk)
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
                print(f'\rDownloading FFMPEG [{colored_bar}] {percent}% {human_dl}/{human_total} {speed:.2f}MB/s ETA {eta_str}', end='', flush=True)
    filled = '+' * bar_width
    colored_filled = ''.join((GREEN + c + RESET) if c == '+' else (RED + c + RESET) for c in filled)
    human_total = f'{total/1024/1024:.2f}MB'
    print(f'\rDownloading FFMPEG [{colored_filled}] 100% {human_total}/{human_total} {speed:.2f}MB/s')
    extract_dir = os.path.join(base_dir, 'temp_ffmpeg_extract')
    if os.path.exists(extract_dir):
        shutil.rmtree(extract_dir)
    os.makedirs(extract_dir, exist_ok=True)
    lower = ffmpeg_url.lower()
    if lower.endswith('.zip'):
        with zipfile.ZipFile(tmp_path, 'r') as z:
            z.extractall(extract_dir)
    elif lower.endswith('.tar.gz') or lower.endswith('.tgz') or lower.endswith('.tar'):
        mode = 'r:gz' if lower.endswith('.gz') or lower.endswith('.tgz') else 'r:'
        with tarfile.open(tmp_path, mode) as t:
            t.extractall(extract_dir)
    else:
        with open(tmp_path, 'rb') as fh:
            sig = fh.read(4)
        if sig[:2] == b'PK':
            with zipfile.ZipFile(tmp_path, 'r') as z:
                z.extractall(extract_dir)
        elif sig[:2] == b'\x1f\x8b':
            with tarfile.open(tmp_path, 'r:gz') as t:
                t.extractall(extract_dir)
        else:
            raise ValueError('Unsupported archive format for ffmpeg download')
    ffmpeg_dir = os.path.join(base_dir, 'ffmpeg')
    if os.path.exists(ffmpeg_dir):
        shutil.rmtree(ffmpeg_dir)
    os.makedirs(ffmpeg_dir, exist_ok=True)
    entries = os.listdir(extract_dir)
    if len(entries) == 1 and os.path.isdir(os.path.join(extract_dir, entries[0])):
        src_root = os.path.join(extract_dir, entries[0])
    else:
        src_root = extract_dir
    for name in os.listdir(src_root):
        src = os.path.join(src_root, name)
        dst = os.path.join(ffmpeg_dir, name)
        if os.path.isdir(src):
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            print(f'Copied directory: {name} to ffmpeg directory')
        else:
            shutil.copy2(src, dst)
            print(f'Copied file: {name} to ffmpeg directory')
            if sys.platform != 'win32' and name == 'ffmpeg':
                os.chmod(dst, 0o755)
    os.remove(tmp_path)
    shutil.rmtree(extract_dir)
    cfg['ffmpeg_url'] = ffmpeg_url
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2)
    print(sep)
    print('ffmpeg downloaded and extracted to ffmpeg directory')
    print(sep)