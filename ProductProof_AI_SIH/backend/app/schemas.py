from typing import List, Optional, Literal
from pydantic import BaseModel, Field

class Listing(BaseModel):
    title:str; description:str=""; brand:Optional[str]=None; category:Optional[str]=None; color:Optional[str]=None; model:Optional[str]=None; sku:Optional[str]=None
class AttributeFinding(BaseModel):
    attribute:str; expected:Optional[str]=None; detected:Optional[str]=None; status:Literal["MATCH","MISMATCH","UNKNOWN"]; confidence:float=Field(ge=0,le=1); evidence:str=""
class ImageAnalysis(BaseModel):
    product_type:Optional[str]=None; brand:Optional[str]=None; model:Optional[str]=None; color:Optional[str]=None; visible_text:List[str]=[]; image_quality:str="unknown"; same_product_likelihood:Optional[float]=None; manipulation_concern:Optional[str]=None
class SimilaritySignal(BaseModel):
    image_text:Optional[float]=None; image_reference:Optional[float]=None; status:str="not_configured"
class Evidence(BaseModel):
    source:str; text:str; relevance:float=0
class VerificationResponse(BaseModel):
    review_id:int; decision:Literal["APPROVE","REVIEW","REJECT"]; correctness_score:float; confidence:float; human_review_required:bool; listing:Listing; attributes:List[AttributeFinding]; image_analysis:List[ImageAnalysis]; ocr_text:List[List[str]]; similarity:List[SimilaritySignal]; product_evidence:List[Evidence]; policy_evidence:List[Evidence]; mismatches:List[str]; explanation:str
class HumanReview(BaseModel):
    decision:Literal["APPROVE","REJECT","REVIEW"]; reviewer_note:str=""
