import os
import shutil
import glob
import threading
import time
import re
import sys
from pathlib import Path
from typing import List, Dict
import json
import subprocess
from .logger import logger
from .background_process import ImageProcessor, ProgressSignal, FileUpdateSignal
from .config_manager import ConfigManager


class VideoUpscalerProcess:
    def __init__(self, base_dir: str, chromedriver_path: str | None = None, config_manager: ConfigManager | None = None,
                 headless: bool | None = None, incognito: bool | None = None, progress_signal: ProgressSignal | None = None,
                 file_update_signal: FileUpdateSignal | None = None):
        self.base_dir = os.path.abspath(base_dir)
        self.chromedriver_path = chromedriver_path
        self.config_manager = config_manager or ConfigManager(self.base_dir)
        self.headless = headless
        self.incognito = incognito
        self.progress_signal = progress_signal or ProgressSignal()
        # allow passing in an external FileUpdateSignal (so UI can react to file updates)
        self.file_update_signal = file_update_signal or FileUpdateSignal()
        self.processor = ImageProcessor(
            chromedriver_path=self.chromedriver_path,
            progress_signal=self.progress_signal,
            file_update_signal=self.file_update_signal,
            config_manager=self.config_manager,
            headless=self.headless,
            incognito=self.incognito
        )
        self.thread: threading.Thread | None = None
        self.should_stop = False

    def _ensure_folder(self, p: Path) -> None:
        if not p.exists():
            os.makedirs(str(p), exist_ok=True)
            logger.info("Created folder", str(p))

    def upscale_hash_sync(self, src_hash_dir: str) -> List[str]:
        src_dir = Path(src_hash_dir)
        if not src_dir.exists() or not src_dir.is_dir():
            logger.kesalahan("Source hash directory not found", str(src_dir))
            raise FileNotFoundError(f"Source hash directory not found: {src_dir}")

        # Use UPSCALE folder inside source hash dir as destination for enhanced frames
        up_dir = src_dir / 'UPSCALE'
        # Ensure UPSCALE is inside the source hash dir and create if missing
        up_dir_res = up_dir.resolve()
        try:
            up_dir_res.relative_to(src_dir.resolve())
        except Exception:
            logger.kesalahan("UPSCALE path outside source hash dir", str(up_dir_res))
            raise RuntimeError(f"Invalid UPSCALE path: {up_dir_res}")
        self._ensure_folder(up_dir)

        hash_name = src_dir.name

        frames = sorted(src_dir.glob('frame_*.png'))
        if not frames:
            logger.kesalahan("No frames found to upscale", str(src_dir))
            raise FileNotFoundError(f"No frames found in: {src_dir}")

        total = len(frames)
        logger.info(f"Starting upscale for {total} frames", str(src_dir))

        successes: List[str] = []
        failures: List[str] = []

        # configure processor for batch processing using config-defined batch_size
        batch_size = int(self.config_manager.get_batch_size())
        if batch_size <= 0:
            batch_size = 1
        self.processor.batch_size = batch_size
        self.processor.should_stop = False

        # Start processing frames in the src_dir as a single batch job
        self.processor.start_processing([str(src_dir)])

        # Wait deterministically for processing to finish or be stopped
        while self.processor.processing_thread and self.processor.processing_thread.is_alive():
            if self.should_stop:
                self.processor.stop_processing()
                logger.kesalahan("Upscale process stopped by user", str(src_dir))
                raise RuntimeError("Upscale process stopped by user")
            time.sleep(0.2)

        # helper: strip timestamp suffixes like _YYYYMMDD_HHMMSS or trailing numeric suffix
        def _strip_suffix(name: str) -> str:
            m = re.search(r'_(\d{8}_\d{6})$', name)
            if m:
                return name[:m.start()]
            m2 = re.search(r'_(\d{6,})$', name)
            if m2:
                return name[:m2.start()]
            return name

        def _build_enhanced_map() -> Dict[str, Path]:
            enh: Dict[str, Path] = {}
            for f in sorted(up_dir.glob('*.*')):
                if not f.is_file():
                    continue
                base = _strip_suffix(f.stem)
                existing = enh.get(base)
                if existing is None or f.stat().st_mtime > existing.stat().st_mtime:
                    enh[base] = f
            return enh

        # initial mapping
        enhanced_map = _build_enhanced_map()
        original_names = [f.stem for f in frames]
        missing = [name for name in original_names if name not in enhanced_map]

        last_missing_count = None
        attempts = 0
        while missing:
            attempts += 1
            print(f"Missing upscaled frames ({len(missing)}): {', '.join(missing)}")
            logger.kesalahan(f"Missing upscaled frames: {len(missing)}", ','.join(missing))

            # re-run upscale for missing frames only
            missing_paths = [str(src_dir / f"{name}.png") for name in missing]
            self.processor.should_stop = False
            self.processor.start_processing(missing_paths)

            # wait for retry processing
            while self.processor.processing_thread and self.processor.processing_thread.is_alive():
                if self.should_stop:
                    self.processor.stop_processing()
                    logger.kesalahan("Upscale process stopped by user", str(src_dir))
                    raise RuntimeError("Upscale process stopped by user")
                time.sleep(0.2)

            enhanced_map = _build_enhanced_map()
            new_missing = [name for name in original_names if name not in enhanced_map]

            if last_missing_count is not None and len(new_missing) >= last_missing_count:
                logger.kesalahan("No progress on missing frames after retry", f"{len(new_missing)} still missing in {src_dir}")
                print(f"No progress on missing frames after retry: {len(new_missing)} remaining")
                raise RuntimeError(f"Unable to upscale all frames; still missing: {', '.join(new_missing)}")

            last_missing_count = len(new_missing)
            missing = new_missing

        # All frames have enhanced outputs; collect the newest enhanced files in original frame order
        for frame in frames:
            enhanced = enhanced_map.get(frame.stem)
            if enhanced is None or not enhanced.exists():
                failures.append(str(frame))
                logger.kesalahan("Enhanced output missing after retries", str(frame))
                continue
            successes.append(str(enhanced))

        if failures:
            msg = f"Upscale finished with failures: {len(failures)} failed out of {total}"
            logger.kesalahan(msg, str(src_dir))
            raise RuntimeError(msg)

        # Merge frames into a single video in the SOURCE video's UPSCALE folder
        meta_path = src_dir / 'meta.json'
        if not meta_path.exists():
            logger.kesalahan("Metadata file for merge not found", str(meta_path))
            raise RuntimeError(f"Missing metadata file required for merging: {meta_path}")

        try:
            with open(meta_path, 'r', encoding='utf-8') as mf:
                meta = json.load(mf)
        except Exception as e:
            logger.kesalahan("Failed to read metadata file", str(e))
            raise

        source_video = meta.get('source_video')
        fps = meta.get('fps')
        if not source_video:
            logger.kesalahan("Source video not present in metadata", str(meta_path))
            raise RuntimeError(f"Source video missing in metadata: {meta_path}")

        source_video_path = Path(source_video)
        if not source_video_path.exists():
            logger.kesalahan("Source video file not found", str(source_video_path))
            raise RuntimeError(f"Source video not found: {source_video_path}")

        dest_video_dir = source_video_path.parent / 'UPSCALE'
        self._ensure_folder(dest_video_dir)
        output_video = dest_video_dir / source_video_path.name

        ffmpeg_bin = os.path.join(self.base_dir, 'ffmpeg', 'ffmpeg.exe') if sys.platform == 'win32' else os.path.join(self.base_dir, 'ffmpeg', 'ffmpeg')
        if not os.path.exists(ffmpeg_bin):
            logger.kesalahan("ffmpeg not found for merging video", ffmpeg_bin)
            raise FileNotFoundError(f"ffmpeg not found: {ffmpeg_bin}")

        merge_tmp = up_dir / f"merge_{int(time.time())}"
        os.makedirs(str(merge_tmp), exist_ok=True)

        # copy enhanced files into merge_tmp with sequential names based on original frame order
        for idx, frame in enumerate(frames, start=1):
            enh = enhanced_map.get(frame.stem)
            if not enh or not enh.exists():
                logger.kesalahan("Missing enhanced file during merge preparation", str(frame))
                raise RuntimeError(f"Missing enhanced file for {frame}")
            ext = enh.suffix.lstrip('.')
            dest_name = f"frame_{idx:08d}.{ext}"
            shutil.copy2(str(enh), str(merge_tmp / dest_name))

        # determine extension and input pattern
        firstfile = next((p for p in sorted(merge_tmp.glob('*'))), None)
        if firstfile is None:
            logger.kesalahan("No files found for merging in temp merge folder", str(merge_tmp))
            raise RuntimeError(f"No files to merge in {merge_tmp}")
        ext = firstfile.suffix.lstrip('.')
        pattern = os.path.join(str(merge_tmp), f"frame_%08d.{ext}")

        # run ffmpeg to concatenate frames into video
        fps_str = str(int(fps)) if isinstance(fps, (int, float)) and float(fps).is_integer() else str(fps)
        cmd = [ffmpeg_bin, '-hide_banner', '-y', '-framerate', fps_str, '-i', pattern, '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(output_video)]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode != 0:
            logger.kesalahan("ffmpeg failed during merge", proc.stderr.strip())
            shutil.rmtree(str(merge_tmp), ignore_errors=True)
            raise RuntimeError(f"ffmpeg merge failed: {proc.stderr.strip()}")

        # cleanup temporary merge folder
        shutil.rmtree(str(merge_tmp), ignore_errors=True)

        # final progress
        self.processor.update_progress(f"Upscale & merge selesai untuk {hash_name}", 100)

        logger.sukses(f"All frames upscaled and merged", str(output_video))
        return successes

    def upscale_hash_async(self, src_hash_dir: str) -> None:
        if self.thread and self.thread.is_alive():
            logger.kesalahan("Upscale already running", str(src_hash_dir))
            raise RuntimeError("Upscale already running")

        def target():
            try:
                self.upscale_hash_sync(src_hash_dir)
            finally:
                self.thread = None

        self.thread = threading.Thread(target=target, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.should_stop = True
        # propagate to processor
        self.processor.should_stop = True
        if self.thread and self.thread.is_alive():
            self.thread.join(10)
            if self.thread.is_alive():
                logger.peringatan("Upscale thread did not stop within timeout", str(self.thread))
