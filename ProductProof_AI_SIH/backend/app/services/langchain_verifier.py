"""Final reasoning pass over the collected evidence, using Gemini via LangChain.

Kept as a LangChain component (structured output) so it composes with the
rest of the RAG pipeline, but now targets Gemini instead of OpenAI, and logs
failures instead of swallowing them silently.
"""
import json
import logging
import os
from typing import List, Literal, Optional

logger = logging.getLogger("productproof.verifier")


def llm_reasoning(listing, attributes, evidence, policy) -> Optional[dict]:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.warning("GOOGLE_API_KEY is not set - skipping LLM reasoning step")
        return None

    try:
        from pydantic import BaseModel, Field
        from langchain_google_genai import ChatGoogleGenerativeAI

        class Verdict(BaseModel):
            decision: Literal["APPROVE", "REVIEW", "REJECT"]
            confidence: float = Field(ge=0, le=1)
            explanation: str
            mismatch_summary: List[str]

        model_name = os.getenv("GEMINI_VERIFIER_MODEL", "gemini-2.0-flash")
        llm = ChatGoogleGenerativeAI(model=model_name, google_api_key=api_key, temperature=0)
        structured = llm.with_structured_output(Verdict)

        prompt = (
            "Verify a marketplace product listing against the evidence collected so "
            "far. Never invent evidence that was not provided to you. If evidence is "
            "missing, weak, or conflicting, choose REVIEW rather than guessing.\n"
            f"LISTING={json.dumps(listing)}\n"
            f"ATTRIBUTE_FINDINGS={json.dumps(attributes)}\n"
            f"PRODUCT_EVIDENCE={json.dumps(evidence)}\n"
            f"POLICY_EVIDENCE={json.dumps(policy)}"
        )
        return structured.invoke(prompt).model_dump()

    except Exception as exc:  # noqa: BLE001
        logger.exception("Gemini reasoning step failed: %s", exc)
        return None
