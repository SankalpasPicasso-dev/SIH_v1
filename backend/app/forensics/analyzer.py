from pathlib import Path
import cv2, numpy as np
from PIL import Image, ExifTags
from app.forensics.config import enabled
from app.forensics.detectors import copy_move, edge_inconsistency, jpeg_blocks, localized_ela, resampling

def _disabled(): return {"enabled": False, "available": False, "score": 0, "suspicious": False, "evidence": []}

def analyze(path: str, artifact_dir: str | Path | None = None):
    img=cv2.imread(path); gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
    # ELA: recompress and compare. A relative signal, never a conclusion.
    temp=str(Path(path).with_suffix(".ela_tmp.jpg")); cv2.imwrite(temp,img,[cv2.IMWRITE_JPEG_QUALITY,90])
    recompressed=cv2.imread(temp); diff=cv2.absdiff(img,recompressed); ela=float(np.mean(diff))
    try: Path(temp).unlink()
    except OSError: pass
    noise=float(np.std(cv2.Laplacian(gray,cv2.CV_64F)))
    edges=cv2.Canny(gray,100,200); suspicious=float(np.mean(edges)/255*100)
    metadata={}; editing_software=None
    try:
      exif=Image.open(path).getexif()
      metadata={ExifTags.TAGS.get(k,str(k)):str(v) for k,v in exif.items()}
      editing_software=metadata.get("Software")
    except Exception: pass
    artifacts = Path(artifact_dir) if artifact_dir else None
    overlay = artifacts / f"{Path(path).stem}_copy_move_overlay.png" if artifacts else None
    advanced = {
      "localized_ela": localized_ela(img) if enabled("localized_ela") else _disabled(),
      "copy_move": copy_move(img, overlay) if enabled("copy_move") else _disabled(),
      "resampling": resampling(img) if enabled("resampling") else _disabled(),
      "jpeg_blocks": jpeg_blocks(img) if enabled("jpeg_blocks") else _disabled(),
      "edge_inconsistency": edge_inconsistency(img) if enabled("edge_inconsistency") else _disabled(),
    }
    signals = [value["score"] for value in advanced.values() if value.get("enabled")]
    confidence = round(max(.5, 1 - (1 if noise < 15 else 0) * .2), 2)
    indicator=min(100, round(ela*3 + max(0,noise-45)*.25 + suspicious*.15 + min(30, sum(signals) * .10),1))
    artifact_urls = [f"/files/{Path(item['overlay_path']).name}" for item in advanced.values() if item.get("overlay_path")]
    return {"ela":{"score":round(ela,2),"interpretation":"Compression-difference indicator; not proof of editing."},"noise":{"score":round(noise,2),"interpretation":"Local noise consistency signal."},"compression":{"score":round(suspicious,2),"interpretation":"Edge/compression characteristic indicator."},"metadata":{"software":editing_software,"available":bool(metadata),"note":"Missing metadata is common and is not fraud evidence."},"suspicious_regions":{"score":round(suspicious,2),"note":"Potentially unusual texture regions require human review."},"advanced":advanced,"confidence":confidence,"artifact_urls":artifact_urls,"indicator_score":indicator,"note":"Forensic signals are review evidence, not proof of editing or fraud."}
