"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import "./globals.css";

const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api/v1";

const FIELD_DEFS = [
  { key: "title", label: "Title", full: true },
  { key: "brand", label: "Brand" },
  { key: "category", label: "Category" },
  { key: "color", label: "Color" },
  { key: "model", label: "Model" },
  { key: "sku", label: "SKU" },
];

export default function Home() {
  const [form, setForm] = useState({
    title: "", description: "", brand: "", category: "", color: "", model: "", sku: "",
  });
  const [images, setImages] = useState([]); // File[]
  const [previews, setPreviews] = useState([]); // objectURL[]
  const [dragActive, setDragActive] = useState(false);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [status, setStatus] = useState(null); // { gemini_configured, vlm_model }
  const fileInputRef = useRef(null);

  const caseId = useMemo(() => {
    const n = Math.floor(Math.random() * 900000 + 100000);
    return `PP-${new Date().getFullYear()}-${n}`;
  }, []);

  useEffect(() => {
    fetch(`${API}/system-status`).then((r) => r.json()).then(setStatus).catch(() => setStatus(null));
  }, []);

  useEffect(() => {
    const urls = images.map((f) => URL.createObjectURL(f));
    setPreviews(urls);
    return () => urls.forEach((u) => URL.revokeObjectURL(u));
  }, [images]);

  function update(e) {
    setForm({ ...form, [e.target.name]: e.target.value });
  }

  function addFiles(fileList) {
    const incoming = Array.from(fileList || []).filter((f) => f.type.startsWith("image/"));
    setImages((prev) => [...prev, ...incoming].slice(0, 8));
  }

  function removeImage(idx) {
    setImages((prev) => prev.filter((_, i) => i !== idx));
  }

  async function verify() {
    setError("");
    if (!form.title.trim()) return setError("Give the listing a title before running verification.");
    if (!images.length) return setError("Upload at least one product photo.");
    setLoading(true);
    setResult(null);
    const body = new FormData();
    Object.entries(form).forEach(([k, v]) => body.append(k, v));
    images.forEach((img) => body.append("images", img));
    try {
      const r = await fetch(`${API}/verify`, { method: "POST", body });
      if (!r.ok) throw new Error(await r.text());
      setResult(await r.json());
    } catch (e) {
      setError(String(e.message || e).slice(0, 400));
    } finally {
      setLoading(false);
    }
  }

  async function review(decision) {
    if (!result) return;
    await fetch(`${API}/reviews/${result.review_id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, reviewer_note: note }),
    });
    setResult({ ...result, decision, human_review_required: false });
  }

  return (
    <main className="container">
      <div className="topbar">
        <div className="brand">
          <div className="brand-mark">PP</div>
          <div className="brand-text">
            <h1>ProductProof AI</h1>
            <p>Marketplace listing image verification</p>
          </div>
        </div>
        <div className="case-id">
          Case <b>{caseId}</b>
        </div>
      </div>

      {status && !status.gemini_configured && (
        <div className="banner">
          <span>&#9888;&#65039;</span>
          <span>
            The backend has no Gemini key configured, so every attribute will read <b>UNKNOWN</b>.
            Add <code>GOOGLE_API_KEY</code> to <code>backend/.env</code> (get a free key at{" "}
            <code>aistudio.google.com/app/apikey</code>) and restart the backend.
          </span>
        </div>
      )}

      <div className="workbench">
        <section className="pane">
          <div className="pane-head">
            <span className="pane-num">01</span>
            <h2>Listing intake</h2>
          </div>
          <div className="pane-body">
            {FIELD_DEFS.map((f) =>
              f.full ? (
                <div key={f.key}>
                  <label className="flabel">{f.label}</label>
                  <input className="field" name={f.key} value={form[f.key]} onChange={update} placeholder="e.g. ExampleTech X1 128GB Black" />
                </div>
              ) : null
            )}
            <div className="field-row">
              {FIELD_DEFS.filter((f) => !f.full).map((f) => (
                <div key={f.key}>
                  <label className="flabel">{f.label}</label>
                  <input className="field" name={f.key} value={form[f.key]} onChange={update} />
                </div>
              ))}
            </div>
            <label className="flabel">Description</label>
            <textarea className="field" name="description" value={form.description} onChange={update} placeholder="Seller-provided description, specs, condition..." />

            <label className="flabel">Product photos ({images.length}/8)</label>
            <div
              className={`dropzone ${dragActive ? "active" : ""}`}
              onClick={() => fileInputRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
              onDragLeave={() => setDragActive(false)}
              onDrop={(e) => { e.preventDefault(); setDragActive(false); addFiles(e.dataTransfer.files); }}
            >
              <p className="dz-title">Drop images here or click to browse</p>
              <p>JPG or PNG, up to 8 photos</p>
              <input ref={fileInputRef} type="file" accept="image/*" multiple onChange={(e) => addFiles(e.target.files)} />
            </div>
            {previews.length > 0 && (
              <div className="thumbs">
                {previews.map((src, i) => (
                  <div className="thumb" key={i}>
                    <img src={src} alt={`upload ${i + 1}`} />
                    <button type="button" onClick={() => removeImage(i)} aria-label="Remove image">&times;</button>
                  </div>
                ))}
              </div>
            )}

            {error && <div className="banner" style={{ marginTop: 14 }}><span>&#9888;&#65039;</span><span>{error}</span></div>}

            <button className="btn" onClick={verify} disabled={loading}>
              {loading && <span className="spinner" />}
              {loading ? "Running verification..." : "Run verification"}
            </button>
          </div>
        </section>

        <section className="pane">
          <div className="pane-head">
            <span className="pane-num">02</span>
            <h2>Verification report</h2>
          </div>
          <div className="pane-body">
            {result ? (
              <Report result={result} note={note} setNote={setNote} onReview={review} />
            ) : (
              <div className="empty">
                <div className="empty-glyph">&#9679; &#9675; &#9679;</div>
                <p>Submit a listing on the left to generate an evidence-backed report.</p>
              </div>
            )}
          </div>
        </section>
      </div>

      <p className="footer-note">ProductProof AI &middot; OCR + Gemini vision + CLIP similarity + RAG policy check</p>
    </main>
  );
}

function TrustRing({ score, tone }) {
  const r = 38;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, score));
  const dash = `${(pct / 100) * c} ${c}`;
  const color = tone === "approve" ? "var(--seal)" : tone === "reject" ? "var(--red)" : "var(--amber)";
  return (
    <div className="ring-wrap">
      <svg viewBox="0 0 92 92">
        <circle className="ring-track" cx="46" cy="46" r={r} />
        <circle className="ring-value" cx="46" cy="46" r={r} stroke={color} strokeDasharray={dash} />
      </svg>
      <div className="ring-label">
        <div>
          <div className="num">{Math.round(pct)}</div>
          <div className="den">/ 100</div>
        </div>
      </div>
    </div>
  );
}

const DECISION_COPY = {
  APPROVE: { stamp: "Approved", tone: "approve" },
  REVIEW: { stamp: "Needs review", tone: "review" },
  REJECT: { stamp: "Rejected", tone: "reject" },
};

const ATTR_ICON = { MATCH: { glyph: "\u2713", cls: "match" }, MISMATCH: { glyph: "\u2715", cls: "mismatch" }, UNKNOWN: { glyph: "?", cls: "unknown" } };

function Report({ result, note, setNote, onReview }) {
  const copy = DECISION_COPY[result.decision] || DECISION_COPY.REVIEW;
  return (
    <div>
      <div className="verdict-row">
        <TrustRing score={result.correctness_score} tone={copy.tone} />
        <div className={`stamp ${copy.tone}`}>{copy.stamp}</div>
        <div className="verdict-meta">
          <span><b>Confidence</b> {(result.confidence * 100).toFixed(0)}%</span>
          <span><b>Mismatches</b> {result.mismatches.length || "none"}</span>
        </div>
      </div>

      <p className="explanation">{result.explanation}</p>

      <h3 className="section-title">Attribute checklist</h3>
      {result.attributes.map((a, i) => {
        const icon = ATTR_ICON[a.status] || ATTR_ICON.UNKNOWN;
        return (
          <div className="attr-row" key={i}>
            <span className={`attr-icon ${icon.cls}`}>{icon.glyph}</span>
            <span className="attr-name">{a.attribute}</span>
            <span className="attr-val"><span className="k">listing</span> {a.expected || "—"}</span>
            <span className="attr-val"><span className="k">image</span> {a.detected || "—"}</span>
          </div>
        );
      })}

      <h3 className="section-title">Evidence</h3>

      <details className="drawer">
        <summary>Gemini vision analysis ({result.image_analysis.length}) <span className="chev">&#8250;</span></summary>
        <div className="drawer-body">
          {result.image_analysis.map((a, i) => (
            <pre className="raw" key={i}>{JSON.stringify(a, null, 2)}</pre>
          ))}
        </div>
      </details>

      <details className="drawer">
        <summary>OCR text on images <span className="chev">&#8250;</span></summary>
        <div className="drawer-body">
          {result.ocr_text.flat().length ? result.ocr_text.flat().join(", ") : <div className="tag-empty">No text detected on the images.</div>}
        </div>
      </details>

      <details className="drawer">
        <summary>Trusted product evidence ({result.product_evidence.length}) <span className="chev">&#8250;</span></summary>
        <div className="drawer-body">
          {result.product_evidence.length ? result.product_evidence.map((e, i) => (
            <div className="evidence-item" key={i}><b>{e.source}</b><div>{e.text}</div></div>
          )) : <div className="tag-empty">No matching entries in the trusted product catalog.</div>}
        </div>
      </details>

      <details className="drawer">
        <summary>Marketplace policy evidence ({result.policy_evidence.length}) <span className="chev">&#8250;</span></summary>
        <div className="drawer-body">
          {result.policy_evidence.length ? result.policy_evidence.map((e, i) => (
            <div className="evidence-item" key={i}><b>{e.source}</b><div>{e.text}</div></div>
          )) : <div className="tag-empty">No policy clauses retrieved for this listing.</div>}
        </div>
      </details>

      {result.human_review_required && (
        <div className="review-box">
          <h3>Human review requested</h3>
          <p>Evidence was inconclusive. Record a reviewer decision to close this case.</p>
          <textarea className="field" placeholder="Reviewer note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
          <div className="review-actions">
            <button className="btn approve-btn" onClick={() => onReview("APPROVE")}>Approve listing</button>
            <button className="btn reject-btn" onClick={() => onReview("REJECT")}>Reject listing</button>
          </div>
        </div>
      )}
    </div>
  );
}
