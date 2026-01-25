import os
import subprocess
import hashlib
import json
from fractions import Fraction
from pathlib import Path
import threading
import shutil
import queue
import re
from typing import Tuple
from .logger import logger

class VideoFrameExtractor:
    def __init__(self, base_dir: str, ffmpeg_path: str | None = None, ffprobe_path: str | None = None, progress_signal=None):
        self.base_dir = base_dir
        self.ffmpeg_path = ffmpeg_path or os.path.join(base_dir, 'ffmpeg', 'ffmpeg.exe')
        self.ffprobe_path = ffprobe_path or os.path.join(base_dir, 'ffmpeg', 'ffprobe.exe')
        self.progress_signal = progress_signal
        self.should_stop = False
        self.processing_thread = None

    def _emit_progress(self, message: str, percentage: int | None = None):
        if self.progress_signal:
            self.progress_signal.progress.emit(message, int(percentage) if percentage is not None else 0)

    def _ensure_tools(self):
        if not os.path.exists(self.ffmpeg_path):
            logger.kesalahan("ffmpeg not found", self.ffmpeg_path)
            raise FileNotFoundError(f"ffmpeg not found at: {self.ffmpeg_path}")
        if not os.path.exists(self.ffprobe_path):
            logger.kesalahan("ffprobe not found", self.ffprobe_path)
            raise FileNotFoundError(f"ffprobe not found at: {self.ffprobe_path}")

    def _compute_hash_dir(self, video_path: str) -> str:
        st = Path(video_path)
        stat = st.stat()
        h = hashlib.sha256()
        h.update(str(st.resolve()).encode('utf-8'))
        h.update(str(stat.st_size).encode('utf-8'))
        h.update(str(int(stat.st_mtime)).encode('utf-8'))
        return h.hexdigest()

    def _get_total_frames(self, video_path: str) -> Tuple[int, float]:
        cmd = [self.ffprobe_path, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=duration,r_frame_rate', '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode != 0:
            logger.kesalahan("ffprobe failed", proc.stderr.strip())
            raise RuntimeError(f"ffprobe failed: {proc.stderr.strip()}")
        lines = [l.strip() for l in proc.stdout.splitlines() if l.strip()]
        if len(lines) < 2:
            logger.kesalahan("ffprobe returned insufficient data", proc.stdout)
            raise RuntimeError("ffprobe did not return duration and frame rate")
        duration_str = None
        r_frame_rate = None
        for ln in lines:
            if '/' in ln and r_frame_rate is None:
                r_frame_rate = ln
            elif duration_str is None:
                try:
                    _ = float(ln)
                    duration_str = ln
                except Exception:
                    if r_frame_rate is None:
                        r_frame_rate = ln
                    else:
                        duration_str = ln
        if duration_str is None or r_frame_rate is None:
            logger.kesalahan("ffprobe returned unexpected output", proc.stdout)
            raise RuntimeError("Unable to parse duration or frame rate from ffprobe output")
        try:
            duration = float(duration_str)
        except Exception:
            logger.kesalahan("Invalid duration from ffprobe", duration_str)
            raise ValueError(f"Invalid duration from ffprobe: {duration_str}")
        try:
            fr = Fraction(r_frame_rate)
            fps = float(fr)
        except Exception:
            logger.kesalahan("Invalid frame rate from ffprobe", r_frame_rate)
            raise ValueError(f"Invalid frame rate from ffprobe: {r_frame_rate}")
        total_frames = int(round(duration * fps))
        if total_frames <= 0:
            logger.kesalahan("Calculated zero frames", f"duration={duration}, fps={fps}")
            raise ValueError("Unable to determine total frames for video")
        return total_frames, fps

    def extract_frames(self, video_path: str, out_root: str):
        self._ensure_tools()
        video_path = os.path.abspath(video_path)
        hash_name = self._compute_hash_dir(video_path)
        out_dir = os.path.join(out_root, hash_name)
        if os.path.exists(out_dir):
            out_root_res = Path(out_root).resolve()
            out_dir_res = Path(out_dir).resolve()
            try:
                out_dir_res.relative_to(out_root_res)
            except Exception as e:
                logger.kesalahan("Output directory exists but is outside expected root", str(out_dir_res))
                raise RuntimeError(f"Refusing to remove directory outside out_root: {out_dir_res}") from e
            logger.info("Output directory exists; removing to overwrite", str(out_dir))
            shutil.rmtree(str(out_dir_res))
            logger.info("Removed existing output directory", str(out_dir))
        os.makedirs(out_dir, exist_ok=False)

        total_frames, fps = self._get_total_frames(video_path)
        self._emit_progress(f"Ekstrak frame: {Path(video_path).name}", 0)

        # Save metadata for downstream processes (e.g., merging)
        try:
            meta = {
                "source_video": os.path.abspath(video_path),
                "fps": fps,
                "total_frames": total_frames
            }
            with open(os.path.join(out_dir, 'meta.json'), 'w', encoding='utf-8') as mf:
                json.dump(meta, mf)
        except Exception as e:
            logger.kesalahan("Gagal menulis meta file", str(e))
            raise

        cmd = [self.ffmpeg_path, '-hide_banner', '-progress', 'pipe:1', '-i', video_path, '-vsync', '0', os.path.join(out_dir, 'frame_%08d.png')]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        frames_extracted = 0
        q = queue.Queue()
        stderr_accum = []

        def _reader(pipe, is_err: bool):
            try:
                for raw in iter(pipe.readline, ''):
                    if raw == '':
                        break
                    q.put((is_err, raw.rstrip('\n')))
            finally:
                try:
                    pipe.close()
                except Exception:
                    pass

        t_out = threading.Thread(target=_reader, args=(proc.stdout, False), daemon=True)
        t_err = threading.Thread(target=_reader, args=(proc.stderr, True), daemon=True)
        t_out.start()
        t_err.start()

        try:
            while True:
                if self.should_stop:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except Exception:
                        proc.kill()
                    logger.info("Ekstraksi frame dihentikan oleh user", video_path)
                    break

                try:
                    is_err, line = q.get(timeout=0.5)
                except queue.Empty:
                    if proc.poll() is not None:
                        # drain remaining queue
                        while not q.empty():
                            is_err, line = q.get_nowait()
                            if is_err:
                                stderr_accum.append(line)
                            # process line below
                            m = re.search(r'frame\s*=\s*(\d+)', line)
                            if m:
                                frame_num = int(m.group(1))
                                if frame_num > frames_extracted:
                                    frames_extracted = frame_num
                                    percent = int((frames_extracted / total_frames) * 100)
                                    if percent > 100:
                                        percent = 100
                                    self._emit_progress(f"Ekstrak frame: {Path(video_path).name} [{frames_extracted}/{total_frames}]", percent)
                                    logger.info(f"Ekstrak frame {frames_extracted}/{total_frames}", Path(video_path).name)
                        break
                    continue

                if is_err:
                    stderr_accum.append(line)

                # parse frame from either stdout (progress) or stderr
                m = re.search(r'frame\s*=\s*(\d+)', line)
                if m:
                    frame_num = int(m.group(1))
                    if frame_num > frames_extracted:
                        frames_extracted = frame_num
                        percent = int((frames_extracted / total_frames) * 100)
                        if percent > 100:
                            percent = 100
                        self._emit_progress(f"Ekstrak frame: {Path(video_path).name} [{frames_extracted}/{total_frames}]", percent)
                        logger.info(f"Ekstrak frame {frames_extracted}/{total_frames}", Path(video_path).name)

                # ffmpeg -progress also emits 'progress=end' when done
                if line.startswith('progress=') and line.split('=',1)[1].strip() == 'end':
                    break
        finally:
            rc = proc.wait()
            if rc != 0:
                logger.kesalahan("ffmpeg failed during extraction", '\n'.join(stderr_accum))
                raise RuntimeError(f"ffmpeg failed: {'; '.join(stderr_accum[-5:])}")

        # verify frames exist
        pngs = sorted(Path(out_dir).glob('frame_*.png'))
        if not pngs:
            logger.kesalahan("No frames extracted", out_dir)
            raise FileNotFoundError(f"No frames extracted into: {out_dir}")

        self._emit_progress(f"Ekstraksi selesai: {Path(video_path).name}", 100)
        logger.sukses("Ekstrak frame selesai", out_dir)
        return out_dir

    def stop(self):
        self.should_stop = True
        # thread join left to the caller
