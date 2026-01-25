import os
import shutil
from pathlib import Path
from .logger import logger


def clean_temp(base_dir: str, subdir: str = 'temp') -> None:
    base = Path(base_dir).resolve()
    if not base.exists() or not base.is_dir():
        logger.kesalahan("Base directory invalid for temp cleanup", str(base))
        raise FileNotFoundError(f"Base directory not found: {base}")

    temp_root = (base / subdir).resolve()

    try:
        temp_root.relative_to(base)
    except Exception:
        logger.kesalahan("Temp root not inside base directory", str(temp_root))
        raise RuntimeError(f"Temp root is outside base dir: {temp_root}")

    if not temp_root.exists():
        os.makedirs(temp_root, exist_ok=True)
        logger.info("Created temp root", str(temp_root))
        return

    entries = list(temp_root.iterdir())
    if not entries:
        logger.info("Temp root already empty", str(temp_root))
        return

    logger.info("Cleaning temp root", str(temp_root))
    for entry in entries:
        p = Path(entry)
        if p.is_dir():
            shutil.rmtree(p)
            logger.info("Removed directory", str(p))
        else:
            p.unlink()
            logger.info("Removed file", str(p))

    logger.sukses("Temp root cleaned", str(temp_root))
