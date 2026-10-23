from pathlib import Path
import cv2
import numpy as np


def is_decodable(path: str) -> bool:
    """True when OpenCV can decode the file as an image.

    Used to reject non-image uploads with a 400 before any model runs. This is
    a cheap pixel decode, not a full preprocess pass.
    """
    img = cv2.imread(path)
    return img is not None and img.size > 0


def preprocess_image(path: str) -> str:
    img = cv2.imread(path)
    if img is None:
        raise ValueError("Image cannot be decoded")
    h, w = img.shape[:2]
    scale = min(1.0, 1280 / max(h, w))
    if scale < 1:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    # A light bilateral filter smooths sensor noise while keeping edges, and
    # is roughly an order of magnitude faster than fastNlMeansDenoisingColored
    # for a negligible difference in downstream OCR/vision quality.
    img = cv2.bilateralFilter(img, d=5, sigmaColor=40, sigmaSpace=40)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(l)
    img = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)
    out = str(Path(path).with_suffix(".processed.jpg"))
    cv2.imwrite(out, img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return out


def image_metrics(path: str) -> dict:
    """Real, measured (not guessed) image-quality signals using OpenCV.

    - sharpness: variance of the Laplacian, a standard blur-detection metric.
      Higher = sharper. Rule of thumb: <60 blurry, 60-150 soft, >150 sharp.
    - fill_ratio: rough estimate of how much of the frame the product
      occupies, via edge detection + the largest contour's bounding box.
      This is a heuristic, not a segmentation model - treat it as approximate.
    """
    img = cv2.imread(path)
    if img is None:
        return {"width": None, "height": None, "sharpness": None, "fill_ratio": None}
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    fill_ratio = None
    try:
        edges = cv2.Canny(gray, 50, 150)
        edges = cv2.dilate(edges, np.ones((5, 5), np.uint8), iterations=1)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            largest = max(contours, key=cv2.contourArea)
            _, _, bw, bh = cv2.boundingRect(largest)
            fill_ratio = round((bw * bh) / (w * h), 3)
    except Exception:
        pass

    return {"width": w, "height": h, "sharpness": round(sharpness, 1), "fill_ratio": fill_ratio}
