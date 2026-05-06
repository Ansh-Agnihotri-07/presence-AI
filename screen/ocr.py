"""
OCR — Text extraction from screenshots using pytesseract.
"""

import logging
from pathlib import Path

logger = logging.getLogger("presence.screen.ocr")


def extract_text(image_path: str) -> str:
    """
    Extract text from an image using Tesseract OCR.

    Args:
        image_path: Path to the screenshot image.

    Returns:
        Extracted text string (may be noisy).
    """
    if not image_path or not Path(image_path).exists():
        logger.warning(f"Image not found: {image_path}")
        return ""

    try:
        import pytesseract
        from PIL import Image
        from core.config import config

        # Set Tesseract path if configured
        if config.TESSERACT_PATH:
            pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_PATH

        img = Image.open(image_path)
        text = pytesseract.image_to_string(img)
        logger.debug(f"OCR extracted {len(text)} chars from {image_path}")
        return text.strip()

    except ImportError:
        logger.error("pytesseract or Pillow not installed — OCR disabled")
        return "[OCR unavailable — install pytesseract and Pillow]"
    except Exception as e:
        logger.error(f"OCR failed: {e}")
        return f"[OCR error: {e}]"