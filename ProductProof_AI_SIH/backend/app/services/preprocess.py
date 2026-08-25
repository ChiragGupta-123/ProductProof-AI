from pathlib import Path
import cv2

def preprocess_image(path:str)->str:
    img=cv2.imread(path)
    if img is None: raise ValueError("Image cannot be decoded")
    h,w=img.shape[:2]; scale=min(1.0,1600/max(h,w))
    if scale<1: img=cv2.resize(img,(int(w*scale),int(h*scale)))
    img=cv2.fastNlMeansDenoisingColored(img,None,3,3,7,21)
    lab=cv2.cvtColor(img,cv2.COLOR_BGR2LAB); l,a,b=cv2.split(lab)
    l=cv2.createCLAHE(clipLimit=2.0,tileGridSize=(8,8)).apply(l)
    img=cv2.cvtColor(cv2.merge([l,a,b]),cv2.COLOR_LAB2BGR)
    out=str(Path(path).with_suffix('.processed.jpg')); cv2.imwrite(out,img,[cv2.IMWRITE_JPEG_QUALITY,92]); return out
