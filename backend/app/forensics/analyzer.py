from pathlib import Path
import cv2, numpy as np
from PIL import Image, ExifTags

def analyze(path: str):
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
    indicator=min(100, round(ela*3 + max(0,noise-45)*.25 + suspicious*.15,1))
    return {"ela":{"score":round(ela,2),"interpretation":"Compression-difference indicator; not proof of editing."},"noise":{"score":round(noise,2),"interpretation":"Local noise consistency signal."},"compression":{"score":round(suspicious,2),"interpretation":"Edge/compression characteristic indicator."},"metadata":{"software":editing_software,"available":bool(metadata),"note":"Missing metadata is common and is not fraud evidence."},"suspicious_regions":{"score":round(suspicious,2),"note":"Potentially unusual texture regions require human review."},"indicator_score":indicator}
