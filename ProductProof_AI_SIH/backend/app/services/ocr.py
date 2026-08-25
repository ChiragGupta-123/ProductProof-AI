def extract_text(path:str)->list[str]:
    try:
        from paddleocr import PaddleOCR
        ocr=PaddleOCR(lang="en")
        result=ocr.predict(path); out=[]
        for page in result:
            data=page.json() if hasattr(page,"json") and callable(page.json) else None
            if isinstance(data,dict): out.extend(map(str,data.get("res",{}).get("rec_texts",[])))
        return out
    except Exception: return []
