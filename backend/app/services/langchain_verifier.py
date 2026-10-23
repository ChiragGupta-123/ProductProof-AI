"""Fast final reasoning/report generation with Groq through LangChain.

Gemini handles vision; Groq handles synthesis so the expensive visual model is
not also responsible for producing the long natural-language report.
"""
import json
import logging

from pydantic import BaseModel, Field

from app.core.config import settings

log = logging.getLogger("productproof.groq")

MAX_EVIDENCE_CHARS = 1500


class ProductReport(BaseModel):
    product_summary: str
    similarity_explanation: str
    quality_explanation: str
    knowledge_summary: str
    potential_issues: list[str] = Field(default_factory=list)
    recommendation: str
    final_explanation: str


def _bounded(value) -> str:
    """Serialize evidence without letting a large RAG chunk blow the context."""
    text = json.dumps(value, indent=2, default=str)
    return text[:MAX_EVIDENCE_CHARS] + ("…" if len(text) > MAX_EVIDENCE_CHARS else "")


def llm_reasoning(listing, attributes, visual, product_evidence, policy_evidence,
                  quality_checks, text_match_pct, image_quality_pct,
                  authenticity, completeness):
    cfg = settings()
    if not cfg.groq_api_key:
        log.warning("GROQ_API_KEY not configured; using deterministic explanation")
        return None
    try:
        from langchain_groq import ChatGroq

        llm = ChatGroq(
            model=cfg.groq_reasoning_model,
            temperature=0,
            api_key=cfg.groq_api_key,
            timeout=cfg.groq_timeout_seconds,
            max_retries=1,
        )
        structured = llm.with_structured_output(ProductReport)
        prompt = f"""
You are ProductProof AI's marketplace product analyst.
Generate a concise but useful report. Never invent facts. Distinguish measured
signals from interpretation. Explain how similar the image is to the seller's
written listing, what the objective image-quality signals mean, what trusted
RAG knowledge says, and any risks.

LISTING:
{_bounded(listing)}

ATTRIBUTE FINDINGS:
{_bounded(attributes)}

VISUAL ANALYSIS:
{_bounded(visual)}

TEXT-IMAGE MATCH PERCENT:
{text_match_pct}

IMAGE QUALITY PERCENT:
{image_quality_pct}

QUALITY CHECKS:
{_bounded(quality_checks)}

DUPLICATE/AUTHENTICITY SIGNAL:
{_bounded(authenticity)}

OBJECT COMPLETENESS:
{_bounded(completeness)}

TRUSTED PRODUCT EVIDENCE (RAG):
{_bounded(product_evidence)}

MARKETPLACE POLICY EVIDENCE (RAG):
{_bounded(policy_evidence)}

Write the report for a marketplace operations reviewer. Mention that pHash/ELA
are heuristics when discussing authenticity. Do not claim authenticity as fact.
"""
        result = structured.invoke(prompt)
        return result.model_dump()
    except Exception as exc:  # noqa: BLE001 - the deterministic report is the fallback
        log.exception("Groq reasoning failed: %s", exc)
        return None
