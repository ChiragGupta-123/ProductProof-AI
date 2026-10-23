"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import "./globals.css";

const API = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:4000/api/v1").replace(/\/+$/, "");
const SELLER_PORTAL = process.env.NEXT_PUBLIC_SELLER_PORTAL_URL || "http://localhost:5173";
const MAX_IMAGES = 8;

const FIELD_DEFS = [
  { key: "brand", label: "Brand" },
  { key: "category", label: "Category" },
  { key: "color", label: "Color" },
  { key: "model", label: "Model" },
];

const EMPTY_FORM = { title: "", description: "", brand: "", category: "", color: "", model: "", sku: "" };

const DECISION_INFO = {
  APPROVE: { tone: "approve", title: "PASS — Ready for publication", sub: "All critical checks cleared. Image meets marketplace standards." },
  REVIEW: { tone: "review", title: "NEEDS REVIEW", sub: "Evidence was inconclusive. A human reviewer should confirm this listing." },
  REJECT: { tone: "reject", title: "FAIL — Do not publish", sub: "Listing attributes conflict with what the images show." },
};

function confidenceLabel(conf) {
  if (conf == null) return "Unknown confidence";
  if (conf >= 0.85) return "High confidence";
  if (conf >= 0.6) return "Medium confidence";
  return "Low confidence";
}

function pctLabel(pct) {
  if (pct == null) return { word: "Not available", cls: "na" };
  if (pct >= 85) return { word: "Excellent", cls: "" };
  if (pct >= 65) return { word: "Good", cls: "" };
  if (pct >= 45) return { word: "Fair", cls: "mid" };
  return { word: "Poor", cls: "low" };
}

function formatDate(value, withTime = false) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return withTime ? date.toLocaleString() : date.toLocaleDateString();
}

async function readError(response) {
  const text = await response.text();
  try {
    const body = JSON.parse(text);
    return body.detail || body.error || text;
  } catch {
    return text.slice(0, 300) || `Request failed (${response.status})`;
  }
}

export default function Home() {
  const [tab, setTab] = useState("analysis");
  const [showForm, setShowForm] = useState(true);

  const [form, setForm] = useState(EMPTY_FORM);
  const [images, setImages] = useState([]);
  const [previews, setPreviews] = useState([]);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef(null);

  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [savingReview, setSavingReview] = useState(false);

  const [status, setStatus] = useState(null);
  const [statusError, setStatusError] = useState(false);

  const [reviews, setReviews] = useState([]);
  const [reviewsLoading, setReviewsLoading] = useState(true);
  const [reviewsError, setReviewsError] = useState("");

  const maxImages = status?.max_images || MAX_IMAGES;

  async function loadStatus() {
    try {
      const response = await fetch(`${API}/system-status`);
      if (!response.ok) throw new Error(await readError(response));
      setStatus(await response.json());
      setStatusError(false);
    } catch {
      setStatus(null);
      setStatusError(true);
    }
  }

  async function loadReviews() {
    setReviewsLoading(true);
    try {
      const response = await fetch(`${API}/reviews`);
      if (!response.ok) throw new Error(await readError(response));
      const data = await response.json();
      setReviews(Array.isArray(data) ? data : []);
      setReviewsError("");
    } catch (e) {
      setReviews([]);
      setReviewsError(String(e.message || e));
    } finally {
      setReviewsLoading(false);
    }
  }

  useEffect(() => {
    loadStatus();
    loadReviews();
  }, []);

  useEffect(() => {
    const urls = images.map((file) => URL.createObjectURL(file));
    setPreviews(urls);
    return () => urls.forEach((url) => URL.revokeObjectURL(url));
  }, [images]);

  function update(event) {
    setForm({ ...form, [event.target.name]: event.target.value });
  }

  function addFiles(fileList) {
    const incoming = Array.from(fileList || []).filter((file) => file.type.startsWith("image/"));
    if (!incoming.length) {
      setError("Only image files are supported (JPG, PNG or WebP).");
      return;
    }
    const remaining = maxImages - images.length;
    if (remaining <= 0) {
      setError(`You can attach up to ${maxImages} photos. Remove one before adding another.`);
      return;
    }
    setImages([...images, ...incoming].slice(0, maxImages));
    setError(incoming.length > remaining ? `Only the first ${maxImages} photos are used.` : "");
  }

  function removeImage(index) {
    setImages((prev) => prev.filter((_, i) => i !== index));
  }

  function startNewAnalysis() {
    setResult(null);
    setError("");
    setNote("");
    setImages([]);
    setForm(EMPTY_FORM);
    setShowForm(true);
    setTab("analysis");
  }

  async function runVerify() {
    setError("");
    if (!form.title.trim()) {
      setError("Give the listing a title before running verification.");
      return;
    }
    if (!images.length) {
      setError("Upload at least one product photo.");
      return;
    }
    setLoading(true);
    const body = new FormData();
    Object.entries(form).forEach(([key, value]) => body.append(key, value));
    images.forEach((image) => body.append("images", image));
    try {
      const response = await fetch(`${API}/verify`, { method: "POST", body });
      if (!response.ok) throw new Error(await readError(response));
      const data = await response.json();
      setResult(data);
      setShowForm(false);
      loadReviews();
    } catch (e) {
      setError(String(e.message || e).slice(0, 500));
    } finally {
      setLoading(false);
    }
  }

  async function submitReview(decision) {
    if (!result || savingReview) return;
    if (result.persisted === false) {
      setError("This analysis was not stored because MongoDB is not configured, so it cannot be reviewed. Add MONGODB_URI to backend/.env and re-run it.");
      return;
    }
    setSavingReview(true);
    setError("");
    try {
      const response = await fetch(`${API}/reviews/${result.review_id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, reviewer_note: note }),
      });
      if (!response.ok) throw new Error(await readError(response));
      const data = await response.json();
      setResult({
        ...result,
        decision: data.decision || decision,
        human_review_required: false,
        reviewer_note: note,
      });
      setNote("");
      loadReviews();
    } catch (e) {
      setError(`Could not save the review decision: ${String(e.message || e)}`.slice(0, 500));
    } finally {
      setSavingReview(false);
    }
  }

  async function viewReview(id) {
    setDetailLoading(true);
    setError("");
    setTab("analysis");
    try {
      const response = await fetch(`${API}/reviews/${id}`);
      if (!response.ok) throw new Error(await readError(response));
      const data = await response.json();
      setImages([]);
      setResult(data);
      setShowForm(false);
    } catch (e) {
      setError(`Could not open that review: ${String(e.message || e)}`.slice(0, 500));
    } finally {
      setDetailLoading(false);
    }
  }

  const stats = useMemo(() => {
    const total = reviews.length;
    const approved = reviews.filter((item) => item.decision === "APPROVE").length;
    const rejected = reviews.filter((item) => item.decision === "REJECT").length;
    const needsReview = reviews.filter((item) => item.human_review_required).length;
    const avgScore = total
      ? (reviews.reduce((sum, item) => sum + (item.correctness_score || 0), 0) / total).toFixed(1)
      : "—";
    const passRate = total ? Math.round((approved / total) * 100) : null;
    return { total, approved, rejected, needsReview, avgScore, passRate };
  }, [reviews]);

  const missing = status
    ? [
        !status.gemini_configured && { key: "gemini", text: "Gemini is not configured — visual attributes will read UNKNOWN. Add GOOGLE_API_KEY to backend/.env." },
        !status.groq_configured && { key: "groq", text: "Groq is not configured — reports use the deterministic explanation instead of the AI narrative. Add GROQ_API_KEY." },
        !status.mongodb_configured && { key: "mongo", text: "MongoDB is not configured — review history, the queue and manual overrides are disabled. Add MONGODB_URI." },
      ].filter(Boolean)
    : [];

  return (
    <div className="app-shell">
      <Sidebar tab={tab} setTab={setTab} onNewAnalysis={startNewAnalysis} />
      <main className="main">
        {statusError && (
          <div className="banner-warn" role="status">
            <span aria-hidden="true">&#9888;&#65039;</span>
            <span>
              Could not reach the API gateway at <code>{API}</code>. Start the Express and FastAPI services, then{" "}
              <button className="link-btn" onClick={loadStatus}>retry</button>.
            </span>
          </div>
        )}

        {missing.length > 0 && (
          <div className="banner-warn" role="status">
            <span aria-hidden="true">&#9888;&#65039;</span>
            <div>
              <b>Backend running with limited capabilities.</b>
              <ul className="banner-list">
                {missing.map((item) => <li key={item.key}>{item.text}</li>)}
              </ul>
            </div>
          </div>
        )}

        {tab === "dashboard" && (
          <Dashboard
            stats={stats}
            reviews={reviews}
            loading={reviewsLoading}
            error={reviewsError}
            onRetry={loadReviews}
            onView={viewReview}
            onNew={startNewAnalysis}
          />
        )}

        {tab === "analysis" && (
          <div>
            <div className="page-head">
              <h1>Analysis</h1>
              <p>Verify a listing&apos;s images against its claimed attributes.</p>
            </div>
            {detailLoading ? (
              <div className="card placeholder-card" role="status">Loading review…</div>
            ) : showForm || !result ? (
              <IntakeForm
                form={form}
                update={update}
                images={images}
                previews={previews}
                addFiles={addFiles}
                removeImage={removeImage}
                dragActive={dragActive}
                setDragActive={setDragActive}
                fileInputRef={fileInputRef}
                onSubmit={runVerify}
                loading={loading}
                error={error}
                maxImages={maxImages}
              />
            ) : (
              <ReportCard
                result={result}
                previewImage={previews[0]}
                note={note}
                setNote={setNote}
                onReview={submitReview}
                onNewAnalysis={startNewAnalysis}
                savingReview={savingReview}
                error={error}
              />
            )}
          </div>
        )}

        {tab === "archive" && (
          <Archive
            title="Archive"
            subtitle="Every listing that has been run through verification."
            reviews={reviews}
            loading={reviewsLoading}
            error={reviewsError}
            onRetry={loadReviews}
            onView={viewReview}
            emptyText="Nothing here yet. Run a verification to build the archive."
          />
        )}
        {tab === "queue" && (
          <Archive
            title="Review Queue"
            subtitle="Listings where the evidence was inconclusive and a human decision is needed."
            reviews={reviews.filter((item) => item.human_review_required)}
            loading={reviewsLoading}
            error={reviewsError}
            onRetry={loadReviews}
            onView={viewReview}
            emptyText="No listings are waiting for review."
          />
        )}
        {tab === "support" && (
          <SupportTab onNew={startNewAnalysis} />
        )}
        {tab === "settings" && (
          <SettingsTab status={status} statusError={statusError} onRetry={loadStatus} />
        )}
      </main>
    </div>
  );
}

function Sidebar({ tab, setTab, onNewAnalysis }) {
  const items = [
    { key: "dashboard", label: "Dashboard", icon: "▦" },
    { key: "analysis", label: "Analysis", icon: "◎" },
    { key: "queue", label: "Review Queue", icon: "⚑" },
    { key: "archive", label: "Archive", icon: "▤" },
  ];
  const bottom = [
    { key: "support", label: "Support", icon: "?" },
    { key: "settings", label: "Settings", icon: "⚙" },
  ];
  return (
    <aside className="sidebar">
      <div className="sb-brand">
        <div className="mark" aria-hidden="true">PP</div>
        <span>ProductProof</span>
      </div>
      <nav className="sb-nav" aria-label="Main navigation">
        {items.map((item) => (
          <button
            key={item.key}
            className={`sb-item ${tab === item.key ? "active" : ""}`}
            onClick={() => setTab(item.key)}
            aria-current={tab === item.key ? "page" : undefined}
          >
            <span className="ic" aria-hidden="true">{item.icon}</span>{item.label}
          </button>
        ))}
      </nav>
      <button className="sb-new" onClick={onNewAnalysis}>+ New Analysis</button>
      <div className="sb-bottom">
        <a className="sb-item seller-link" href={SELLER_PORTAL} target="_blank" rel="noreferrer">
          <span className="ic" aria-hidden="true">↗</span>Seller Portal
        </a>
        {bottom.map((item) => (
          <button
            key={item.key}
            className={`sb-item ${tab === item.key ? "active" : ""}`}
            onClick={() => setTab(item.key)}
            aria-current={tab === item.key ? "page" : undefined}
          >
            <span className="ic" aria-hidden="true">{item.icon}</span>{item.label}
          </button>
        ))}
      </div>
    </aside>
  );
}

function Dashboard({ stats, reviews, loading, error, onRetry, onView, onNew }) {
  return (
    <div>
      <div className="page-head">
        <h1>Dashboard</h1>
        <p>Live totals computed from your verification history.</p>
      </div>
      <div className="stat-grid">
        <StatCard label="Total analyzed" value={stats.total} />
        <StatCard label="Pass rate" value={stats.passRate == null ? "—" : `${stats.passRate}%`} sub="Share of listings approved" />
        <StatCard label="Avg. correctness score" value={stats.avgScore} />
        <StatCard label="Awaiting human review" value={stats.needsReview} sub={`${stats.rejected} rejected overall`} />
      </div>
      <div className="card">
        <div className="qc-head"><h3>Recent analyses</h3></div>
        {error ? (
          <div className="placeholder-card">
            <p>Review history is unavailable.</p>
            <p className="muted">{error}</p>
            <button className="btn-ghost" onClick={onRetry}>Retry</button>
          </div>
        ) : loading ? (
          <div className="placeholder-card" role="status">Loading…</div>
        ) : reviews.length === 0 ? (
          <div className="placeholder-card">
            No analyses yet. <button className="link-btn" onClick={onNew}>Run your first one</button>.
          </div>
        ) : (
          <ReviewTable reviews={reviews.slice(0, 6)} onView={onView} />
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value, sub }) {
  return (
    <div className="card stat-card">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}

function Archive({ title, subtitle, reviews, loading, error, onRetry, onView, emptyText }) {
  return (
    <div>
      <div className="page-head">
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      <div className="card">
        {error ? (
          <div className="placeholder-card">
            <p>Review history is unavailable.</p>
            <p className="muted">{error}</p>
            <button className="btn-ghost" onClick={onRetry}>Retry</button>
          </div>
        ) : loading ? (
          <div className="placeholder-card" role="status">Loading…</div>
        ) : reviews.length === 0 ? (
          <div className="placeholder-card">{emptyText}</div>
        ) : (
          <ReviewTable reviews={reviews} onView={onView} />
        )}
      </div>
    </div>
  );
}

function ReviewTable({ reviews, onView }) {
  return (
    <div className="table-wrap">
      <table className="data-table">
        <caption className="sr-only">Verification history</caption>
        <thead>
          <tr>
            <th scope="col">Listing</th>
            <th scope="col">Decision</th>
            <th scope="col">Score</th>
            <th scope="col">Confidence</th>
            <th scope="col">Date</th>
            <th scope="col"><span className="sr-only">Actions</span></th>
          </tr>
        </thead>
        <tbody>
          {reviews.map((review) => (
            <tr key={review.id}>
              <td>{review.title || "Untitled listing"}</td>
              <td><DecisionPill decision={review.decision} /></td>
              <td>{Math.round(review.correctness_score || 0)}</td>
              <td>{Math.round((review.confidence || 0) * 100)}%</td>
              <td>{formatDate(review.created_at)}</td>
              <td><button className="link-btn" onClick={() => onView(review.id)}>View</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DecisionPill({ decision }) {
  const info = DECISION_INFO[decision] || DECISION_INFO.REVIEW;
  const label = decision === "APPROVE" ? "Approved" : decision === "REJECT" ? "Rejected" : "Review";
  return <span className={`pill ${info.tone}`}>{label}</span>;
}

function SupportTab({ onNew }) {
  return (
    <div>
      <div className="page-head">
        <h1>Support</h1>
        <p>How scoring works and what to do when a decision looks wrong.</p>
      </div>
      <div className="card support-card">
        <h3>Reading a report</h3>
        <p>Each report separates measured signals from interpretation. Similarity and quality numbers are computed from the images; the narrative is generated only after those measurements.</p>
        <h3>When the evidence is inconclusive</h3>
        <p>Listings land in the Review Queue when confidence is too low for an automatic decision. Open the report, inspect the evidence drawers, then approve or reject with a note.</p>
        <h3>Authenticity signals</h3>
        <p>Perceptual hashing (pHash) and error-level analysis are heuristics, not proof. Treat duplicate or manipulation flags as reasons to look closer.</p>
        <button className="btn-solid" onClick={onNew}>Run a new analysis</button>
      </div>
    </div>
  );
}

function SettingsTab({ status, statusError, onRetry }) {
  if (statusError) {
    return (
      <div>
        <div className="page-head"><h1>Settings</h1></div>
        <div className="card placeholder-card">
          Backend status is unavailable. <button className="link-btn" onClick={onRetry}>Retry</button>
        </div>
      </div>
    );
  }
  if (!status) {
    return (
      <div>
        <div className="page-head"><h1>Settings</h1></div>
        <div className="card placeholder-card" role="status">Loading configuration…</div>
      </div>
    );
  }
  const rows = [
    ["Gemini vision", status.gemini_configured ? "Configured" : "Missing GOOGLE_API_KEY"],
    ["Groq reasoning", status.groq_configured ? "Configured" : "Missing GROQ_API_KEY"],
    ["MongoDB storage", status.mongodb_configured ? "Configured" : "Missing MONGODB_URI"],
    ["Approve threshold", status.thresholds?.approve],
    ["Review threshold", status.thresholds?.review],
    ["Minimum auto confidence", status.thresholds?.min_auto_confidence],
    ["Max images", `${status.max_images} × ${status.max_image_mb} MB`],
    ["Object detector", status.yolo_available ? status.yolo_model : "Ultralytics not installed"],
    ["OCR languages", (status.ocr_languages || []).join(", ") || "—"],
    ["CLIP similarity", status.clip_available ? "Available" : "Transformers not installed"],
  ];
  return (
    <div>
      <div className="page-head">
        <h1>Settings</h1>
        <p>Effective backend configuration. Edit <code>backend/.env</code> and restart to change these.</p>
      </div>
      <div className="card settings-card">
        {rows.map(([label, value]) => (
          <div className="settings-row" key={label}>
            <span className="a-name">{label}</span>
            <span className="a-vals">{String(value)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function IntakeForm({ form, update, images, previews, addFiles, removeImage, dragActive, setDragActive, fileInputRef, onSubmit, loading, error, maxImages }) {
  return (
    <div className="card form-card">
      <label className="flabel" htmlFor="title">Title</label>
      <input id="title" className="field" name="title" value={form.title} onChange={update} placeholder="e.g. Premium Leather Jacket" maxLength={200} />

      <div className="field-row2">
        {FIELD_DEFS.map((field) => (
          <div key={field.key}>
            <label className="flabel" htmlFor={field.key}>{field.label}</label>
            <input id={field.key} className="field" name={field.key} value={form[field.key]} onChange={update} maxLength={120} />
          </div>
        ))}
      </div>

      <label className="flabel" htmlFor="description">Description</label>
      <textarea id="description" className="field" name="description" value={form.description} onChange={update} placeholder="Seller-provided description, specs, condition..." maxLength={5000} />

      <label className="flabel" htmlFor="sku">SKU (optional)</label>
      <input id="sku" className="field" name="sku" value={form.sku} onChange={update} maxLength={120} />

      <span className="flabel" id="photos-label">Product photos ({images.length}/{maxImages})</span>
      <div
        className={`dropzone ${dragActive ? "active" : ""}`}
        role="button"
        tabIndex={0}
        aria-labelledby="photos-label"
        onClick={() => fileInputRef.current?.click()}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            fileInputRef.current?.click();
          }
        }}
        onDragOver={(event) => { event.preventDefault(); setDragActive(true); }}
        onDragLeave={() => setDragActive(false)}
        onDrop={(event) => { event.preventDefault(); setDragActive(false); addFiles(event.dataTransfer.files); }}
      >
        <p className="dz-title">Drop images here or click to browse</p>
        <p>JPG, PNG or WebP · up to {maxImages} photos</p>
        <input
          ref={fileInputRef}
          id="image-input"
          type="file"
          accept="image/jpeg,image/png,image/webp"
          multiple
          aria-hidden="true"
          tabIndex={-1}
          onChange={(event) => {
            addFiles(event.target.files);
            event.target.value = "";
          }}
        />
      </div>
      {previews.length > 0 && (
        <div className="thumbs">
          {previews.map((src, index) => (
            <div className="thumb" key={src}>
              <img src={src} alt={`Upload preview ${index + 1}`} />
              <button type="button" onClick={() => removeImage(index)} aria-label={`Remove photo ${index + 1}`}>&times;</button>
            </div>
          ))}
        </div>
      )}
      {error && <div className="banner-warn inline" role="alert"><span aria-hidden="true">&#9888;&#65039;</span><span>{error}</span></div>}
      <button className="btn-primary" onClick={onSubmit} disabled={loading}>
        {loading && <span className="spinner" aria-hidden="true" />}
        {loading ? "Running verification…" : "Run verification"}
      </button>
    </div>
  );
}

function SignalCard({ label, value, sub }) {
  return (
    <div className="metric-card">
      <div className="m-label">{label}</div>
      <div className="m-value signal-value">{value}</div>
      <div className="m-sub na">{sub}</div>
    </div>
  );
}

function ReportCard({ result, previewImage, note, setNote, onReview, onNewAnalysis, savingReview, error }) {
  const decision = result.decision || "REVIEW";
  const info = DECISION_INFO[decision] || DECISION_INFO.REVIEW;
  const ringColor = info.tone === "approve" ? "var(--green)" : info.tone === "reject" ? "var(--red)" : "var(--amber)";
  const score = Math.max(0, Math.min(100, Number(result.correctness_score) || 0));
  const circumference = 2 * Math.PI * 42;
  const dash = `${(score / 100) * circumference} ${circumference}`;
  const attributes = result.attributes || [];
  const checks = result.quality_checks || [];
  const passedCount = checks.filter((check) => check.passed).length;
  const textMatch = pctLabel(result.text_image_match_pct);
  const imgQuality = pctLabel(result.image_quality_pct);
  const duplicates = result.authenticity || [];
  const completeness = result.completeness || [];
  const manipulation = result.manipulation || [];
  const llmReport = result.llm_report || null;
  const ocrText = (result.ocr_text || []).flat();
  const persisted = result.persisted !== false;
  const completenessStatus = completeness.length === 0
    ? "Not scored"
    : completeness.some((item) => item.status === "REVIEW")
      ? "Missing item"
      : completeness.every((item) => item.status === "NOT_AVAILABLE" || item.status === "NOT_APPLICABLE")
        ? "Not scored"
        : "Pass";
  const severity = { high: 3, medium: 2, low: 1, none: 0 };
  const manipulationConcern = manipulation.reduce((worst, item) => {
    const rank = severity[item.concern] ?? -1;
    return rank > (severity[worst] ?? -1) ? item.concern : worst;
  }, "unknown");

  return (
    <div className="card">
      {error && <div className="banner-warn inline" role="alert"><span aria-hidden="true">&#9888;&#65039;</span><span>{error}</span></div>}

      <div className="report-top">
        <div className="thumb-lg">
          {previewImage ? (
            <img src={previewImage} alt={`Preview of ${result.listing?.title || "the listing"}`} />
          ) : (
            <div className="thumb-empty">No preview available</div>
          )}
        </div>
        <div className="report-mid">
          <div className="report-tags">
            <span className="tag-id">ID: {persisted ? `RVW-${result.review_id}` : "not stored"}</span>
            <span className="pill muted-pill">Analyzed</span>
            {result.created_at && <span className="tag-id">{formatDate(result.created_at, true)}</span>}
          </div>
          <h2>{result.listing?.title || "Untitled listing"}</h2>
          {result.listing?.description && <p className="desc">{result.listing.description}</p>}
          <div className="chips">
            {attributes.length === 0 ? (
              <span className="chip unknown">No attribute findings</span>
            ) : attributes.map((attribute) => {
              const cls = attribute.status === "MATCH" ? "match" : attribute.status === "MISMATCH" ? "mismatch" : "unknown";
              const icon = attribute.status === "MATCH" ? "✓" : attribute.status === "MISMATCH" ? "✕" : "?";
              return (
                <span className={`chip ${cls}`} key={attribute.attribute}>
                  <span aria-hidden="true">{icon}</span>
                  {attribute.attribute}: {attribute.detected || attribute.expected || "—"}
                </span>
              );
            })}
          </div>
        </div>
        <div className="report-right">
          <div className="r-label">Overall Correctness</div>
          <div className="ring-wrap">
            <svg viewBox="0 0 100 100" aria-hidden="true">
              <circle className="ring-track" cx="50" cy="50" r="42" />
              <circle className="ring-value" cx="50" cy="50" r="42" stroke={ringColor} strokeDasharray={dash} />
            </svg>
            <div className="ring-num">{Math.round(score)}</div>
          </div>
          <div className="conf-pill"><span className={`pill ${info.tone}`}>{confidenceLabel(result.confidence)}</span></div>
        </div>
      </div>

      <div className="mid-grid">
        <div className="metric-card">
          <div className="m-label">Text-Image Match</div>
          <div className="m-value">{result.text_image_match_pct == null ? "—" : `${Math.round(result.text_image_match_pct)}%`}</div>
          <div className={`m-sub ${textMatch.cls}`}>{textMatch.word}</div>
        </div>
        <div className="metric-card">
          <div className="m-label">Image Quality</div>
          <div className="m-value">{result.image_quality_pct == null ? "—" : `${Math.round(result.image_quality_pct)}%`}</div>
          <div className={`m-sub ${imgQuality.cls}`}>{imgQuality.word}</div>
        </div>
      </div>

      <div className="signal-grid">
        <SignalCard label="Duplicate risk" value={duplicates.some((item) => item.duplicate) ? "Flagged" : "Clear"} sub="pHash similarity" />
        <SignalCard label="Completeness" value={completenessStatus} sub="Object detection" />
        <SignalCard label="Manipulation signal" value={manipulationConcern === "unknown" ? "Not scored" : manipulationConcern} sub="ELA heuristic" />
        <SignalCard label="Reference match" value={result.similarity?.some?.((item) => item.image_reference != null) ? "Available" : "Not configured"} sub="CLIP image-to-reference" />
      </div>

      {result.mismatches?.length > 0 && (
        <div className="callout danger">
          <b>Attribute conflicts</b>
          <ul>
            {result.mismatches.map((mismatch) => <li key={mismatch}>{mismatch}</li>)}
          </ul>
        </div>
      )}

      <div className="quote-box">
        <p>&ldquo;{result.explanation || "No explanation was generated for this analysis."}&rdquo;</p>
        <div className="quote-attr">{llmReport ? "🤖 Groq + LangChain analyst" : "Deterministic summary (Groq not configured)"}</div>
      </div>

      {llmReport && (
        <div className="ai-report-grid">
          {llmReport.product_summary && <div className="metric-card"><div className="m-label">Product summary</div><div className="report-copy">{llmReport.product_summary}</div></div>}
          {llmReport.similarity_explanation && <div className="metric-card"><div className="m-label">Similarity interpretation</div><div className="report-copy">{llmReport.similarity_explanation}</div></div>}
          {llmReport.quality_explanation && <div className="metric-card"><div className="m-label">Quality interpretation</div><div className="report-copy">{llmReport.quality_explanation}</div></div>}
          {llmReport.knowledge_summary && <div className="metric-card"><div className="m-label">Trusted knowledge</div><div className="report-copy">{llmReport.knowledge_summary}</div></div>}
          {llmReport.potential_issues?.length > 0 && (
            <div className="metric-card">
              <div className="m-label">Potential issues</div>
              <ul className="report-list">{llmReport.potential_issues.map((item) => <li key={item}>{item}</li>)}</ul>
            </div>
          )}
          {llmReport.recommendation && <div className="metric-card"><div className="m-label">Recommendation</div><div className="report-copy">{llmReport.recommendation}</div></div>}
        </div>
      )}

      <div className="qc-card">
        <div className="qc-head">
          <h3>Quality Checks</h3>
          <span className="qc-frac">{passedCount}/{checks.length} Passed</span>
        </div>
        {checks.length === 0 ? (
          <div className="qc-empty">No quality metrics were computed for these images.</div>
        ) : (
          checks.map((check) => (
            <div className="qc-row" key={check.label}>
              <span className={`qc-check ${check.passed ? "pass" : "fail"}`} aria-hidden="true">{check.passed ? "✓" : "✕"}</span>
              <div>
                <div className="qc-label">{check.label}</div>
                <div className="qc-detail">{check.detail}</div>
              </div>
            </div>
          ))
        )}
      </div>

      <div className="attr-table">
        {attributes.length === 0 ? (
          <p className="muted">No attribute comparison was produced.</p>
        ) : attributes.map((attribute) => (
          <div className="attr-row-line" key={attribute.attribute}>
            <span className="a-name">{attribute.attribute}</span>
            <span className="a-vals">listing: {attribute.expected || "—"} · image: {attribute.detected || "—"} · {attribute.status}</span>
          </div>
        ))}
      </div>

      <div className="evidence-wrap">
        <details className="drawer">
          <summary>Gemini vision analysis ({result.image_analysis?.length || 0})</summary>
          <div className="drawer-body">
            {(result.image_analysis || []).length === 0
              ? "No visual analysis was recorded."
              : result.image_analysis.map((item, index) => <pre className="raw" key={index}>{JSON.stringify(item, null, 2)}</pre>)}
          </div>
        </details>
        <details className="drawer">
          <summary>OCR text on images ({ocrText.length})</summary>
          <div className="drawer-body">{ocrText.length ? ocrText.join(", ") : "No text detected."}</div>
        </details>
        <details className="drawer">
          <summary>Trusted product evidence ({result.product_evidence?.length || 0})</summary>
          <div className="drawer-body">
            {(result.product_evidence || []).length
              ? result.product_evidence.map((evidence, index) => <div key={index}><b>{evidence.source}:</b> {evidence.text}</div>)
              : "None retrieved."}
          </div>
        </details>
        <details className="drawer">
          <summary>Marketplace policy evidence ({result.policy_evidence?.length || 0})</summary>
          <div className="drawer-body">
            {(result.policy_evidence || []).length
              ? result.policy_evidence.map((evidence, index) => <div key={index}><b>{evidence.source}:</b> {evidence.text}</div>)
              : "None retrieved."}
          </div>
        </details>
        {result.review_history?.length > 0 && (
          <details className="drawer">
            <summary>Review history ({result.review_history.length})</summary>
            <div className="drawer-body">
              {result.review_history.map((entry, index) => (
                <div key={index}>
                  <b>{entry.decision}</b> · {formatDate(entry.reviewed_at, true)}
                  {entry.reviewer_note ? ` — ${entry.reviewer_note}` : ""}
                </div>
              ))}
            </div>
          </details>
        )}
      </div>

      {result.human_review_required && (
        <div className="review-note">
          {persisted ? (
            <>
              <label className="flabel" htmlFor="reviewer-note">Reviewer note (optional)</label>
              <textarea id="reviewer-note" className="field" value={note} onChange={(event) => setNote(event.target.value)} maxLength={1000} />
            </>
          ) : (
            <p className="muted">This analysis was not stored, so it cannot be reviewed.</p>
          )}
        </div>
      )}

      <div className={`decision-banner ${info.tone}`}>
        <div className="db-text">
          <b>{info.title}</b>
          <span>{info.sub}</span>
        </div>
        <div className="db-actions">
          {result.human_review_required ? (
            <>
              <button className="btn-solid red" onClick={() => onReview("REJECT")} disabled={savingReview || !persisted}>Reject listing</button>
              <button className="btn-solid green" onClick={() => onReview("APPROVE")} disabled={savingReview || !persisted}>
                {savingReview ? "Saving…" : "Approve listing"}
              </button>
            </>
          ) : (
            <button className="btn-ghost" onClick={onNewAnalysis}>New analysis</button>
          )}
        </div>
      </div>
    </div>
  );
}
