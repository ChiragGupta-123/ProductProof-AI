import json,os,shutil,tempfile
from fastapi import APIRouter,UploadFile,File,Form,HTTPException
from app.models.db import SessionLocal,VerificationRecord
from app.schemas import HumanReview
from app.services.preprocess import preprocess_image
from app.services.ocr import extract_text
from app.services.vlm import analyze
from app.services.verification import verify

router=APIRouter()
@router.get("/health")
def health():return {"status":"ok"}

@router.post("/verify")
async def verify_listing(title:str=Form(...),description:str=Form(""),brand:str=Form(""),category:str=Form(""),color:str=Form(""),model:str=Form(""),sku:str=Form(""),images:list[UploadFile]=File(...)):
    if not images:raise HTTPException(400,"At least one image is required")
    if len(images)>8:raise HTTPException(400,"Maximum 8 images")
    listing={"title":title,"description":description,"brand":brand or None,"category":category or None,"color":color or None,"model":model or None,"sku":sku or None}
    os.makedirs(os.getenv("UPLOAD_DIR","./data/uploads"),exist_ok=True); paths=[]; ocr=[]; vision=[]
    for image in images:
        suffix=os.path.splitext(image.filename or ".jpg")[1]
        with tempfile.NamedTemporaryFile(delete=False,suffix=suffix,dir=os.getenv("UPLOAD_DIR","./data/uploads")) as tmp: shutil.copyfileobj(image.file,tmp); raw=tmp.name
        p=preprocess_image(raw); paths.append(p); ocr.append(extract_text(p)); vision.append(analyze(p,listing))
    r=verify(listing,paths,ocr,vision)
    payload={"listing":listing,"decision":r["decision"],"correctness_score":r["correctness_score"],"confidence":r["confidence"],"human_review_required":r["human_review_required"],"attributes":r["attributes"],"image_analysis":vision,"ocr_text":ocr,"similarity":r["similarities"],"product_evidence":r["product_evidence"],"policy_evidence":r["policy_evidence"],"mismatches":r["mismatches"],"explanation":r["explanation"]}
    db=SessionLocal(); rec=VerificationRecord(title=title,decision=r["decision"],correctness_score=r["correctness_score"],confidence=r["confidence"],human_review_required=r["human_review_required"],result_json=json.dumps(payload)); db.add(rec); db.commit(); db.refresh(rec); db.close(); payload["review_id"]=rec.id; return payload

@router.post("/reviews/{review_id}")
def human_review(review_id:int,review:HumanReview):
    db=SessionLocal(); rec=db.get(VerificationRecord,review_id)
    if not rec: db.close(); raise HTTPException(404,"Review not found")
    rec.decision=review.decision; rec.reviewer_note=review.reviewer_note; rec.human_review_required=False; db.commit(); db.close(); return {"status":"updated","review_id":review_id,"decision":review.decision}

@router.get("/reviews")
def reviews():
    db=SessionLocal(); rows=db.query(VerificationRecord).order_by(VerificationRecord.created_at.desc()).limit(100).all(); out=[{"id":r.id,"created_at":r.created_at.isoformat(),"title":r.title,"decision":r.decision,"correctness_score":r.correctness_score,"confidence":r.confidence,"human_review_required":r.human_review_required,"reviewer_note":r.reviewer_note} for r in rows]; db.close(); return out
