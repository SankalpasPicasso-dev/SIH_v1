from pathlib import Path
import cv2, numpy as np

UPLOAD_DIR = Path(__file__).resolve().parents[3] / "data" / "uploads"; UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

def preprocess(path: str):
    original = cv2.imread(path)
    if original is None: raise ValueError("Image could not be decoded")
    h,w=original.shape[:2]; scale=min(1.8, max(1, 1600/max(w,h)))
    if scale != 1: original=cv2.resize(original,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC)
    gray=cv2.cvtColor(original,cv2.COLOR_BGR2GRAY)
    denoise=cv2.fastNlMeansDenoising(gray,None,8,7,21)
    clahe=cv2.createCLAHE(clipLimit=2.5,tileGridSize=(8,8)).apply(denoise)
    sharp=cv2.addWeighted(clahe,1.5,cv2.GaussianBlur(clahe,(0,0),2),-.5,0)
    # Different scans respond differently to thresholding. Keep the original
    # upload intact and let OCR choose between a natural enhanced image and a
    # thresholded text-focused variant rather than assuming one is always best.
    threshold=cv2.adaptiveThreshold(sharp,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY,31,9)
    base=Path(path).stem; enhanced=str(UPLOAD_DIR/f"{base}_enhanced.png"); ocr=str(UPLOAD_DIR/f"{base}_ocr.png"); threshold_path=str(UPLOAD_DIR/f"{base}_threshold_ocr.png")
    cv2.imwrite(enhanced,sharp); cv2.imwrite(ocr,sharp); cv2.imwrite(threshold_path,threshold)
    return {"width":w,"height":h,"quality":"adequate" if min(w,h)>=500 else "limited","enhanced_path":enhanced,"ocr_path":ocr,"ocr_paths":[ocr,threshold_path]}
