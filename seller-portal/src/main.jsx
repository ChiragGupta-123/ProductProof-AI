import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

const API = (import.meta.env.VITE_API_URL || "http://localhost:4000/api/v1").replace(/\/+$/, "");
const MAX_IMAGES = 8;
const EMPTY_FORM = { title: "", description: "", brand: "", category: "", color: "", model: "" };

const DECISION = {
  APPROVE: {
    title: "Looks ready to publish",
    detail: "The images and listing details agree, and no blocking issues were detected.",
  },
  REVIEW: {
    title: "Needs a closer look",
    detail: "The evidence was inconclusive, so a marketplace reviewer may check this listing.",
  },
  REJECT: {
    title: "Do not publish yet",
    detail: "The images conflict with the listing details. Update the photos or the description.",
  },
};

async function readError(response) {
  const text = await response.text();
  try {
    const body = JSON.parse(text);
    return body.detail || body.error || text;
  } catch {
    return text.slice(0, 300) || `Request failed (${response.status})`;
  }
}

function App() {
  const [form, setForm] = useState(EMPTY_FORM);
  const [files, setFiles] = useState([]);
  const [previews, setPreviews] = useState([]);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [error, setError] = useState("");
  const cameraRef = useRef(null);
  const galleryRef = useRef(null);

  useEffect(() => {
    const urls = files.map((file) => URL.createObjectURL(file));
    setPreviews(urls);
    return () => urls.forEach((url) => URL.revokeObjectURL(url));
  }, [files]);

  function field(key) {
    return (event) => setForm((previous) => ({ ...previous, [key]: event.target.value }));
  }

  function addFiles(fileList) {
    const incoming = Array.from(fileList || []).filter((file) => file.type.startsWith("image/"));
    if (!incoming.length) {
      setError("Choose an image file (JPG, PNG or WebP).");
      return;
    }
    const remaining = MAX_IMAGES - files.length;
    if (remaining <= 0) {
      setError(`You can attach up to ${MAX_IMAGES} photos. Remove one first.`);
      return;
    }
    setFiles([...files, ...incoming].slice(0, MAX_IMAGES));
    setError(incoming.length > remaining ? `Only the first ${MAX_IMAGES} photos are used.` : "");
  }

  function removeFile(index) {
    setFiles(files.filter((_, i) => i !== index));
  }

  function listen() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setError("Voice input is not supported in this browser. Type the description instead.");
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.lang = navigator.language?.toLowerCase().startsWith("en") ? navigator.language : "en-IN";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onresult = (event) => {
      const transcript = Array.from(event.results).map((item) => item[0].transcript).join(" ").trim();
      if (!transcript) return;
      setForm((previous) => ({
        ...previous,
        description: `${previous.description} ${transcript}`.trim(),
      }));
    };
    recognition.onerror = (event) => {
      setError(
        event.error === "not-allowed"
          ? "Microphone access was denied. Allow it in your browser settings and try again."
          : `Voice input stopped: ${event.error}.`
      );
    };
    recognition.onend = () => setListening(false);
    setError("");
    setListening(true);
    try {
      recognition.start();
    } catch {
      setListening(false);
      setError("Voice input could not start. Try again.");
    }
  }

  function speak() {
    const text = result?.llm_report?.final_explanation || result?.explanation;
    if (!text) {
      setError("There is no report text to read aloud yet.");
      return;
    }
    if (!("speechSynthesis" in window)) {
      setError("Speech playback is not supported in this browser.");
      return;
    }
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
  }

  async function submit(event) {
    event.preventDefault();
    setError("");
    if (!form.title.trim()) {
      setError("Add a listing title before running the check.");
      return;
    }
    if (!files.length) {
      setError("Attach at least one product photo.");
      return;
    }
    setBusy(true);
    const body = new FormData();
    Object.entries(form).forEach(([key, value]) => body.append(key, value));
    files.forEach((file) => body.append("images", file));
    try {
      const response = await fetch(`${API}/verify`, { method: "POST", body });
      if (!response.ok) throw new Error(await readError(response));
      setResult(await response.json());
    } catch (err) {
      setError(`Could not verify this listing: ${String(err.message || err)}`.slice(0, 500));
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setResult(null);
    setError("");
    setForm(EMPTY_FORM);
    setFiles([]);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  return (
    <div className="wrap">
      <header className="topbar">
        <div className="brand">
          <span className="mark" aria-hidden="true">PP</span>
          <span>ProductProof AI</span>
        </div>
        <span className="tag">Seller Portal</span>
      </header>

      <section className="hero">
        <h1>Check your listing before you publish</h1>
        <p>
          Upload your product photos and the details you plan to publish. We compare them with
          independent visual analysis and flag anything a buyer or reviewer might question.
        </p>
      </section>

      {error && (
        <div className="alert" role="alert">
          <span aria-hidden="true">⚠️</span>
          <span>{error}</span>
          <button type="button" className="alert-close" onClick={() => setError("")} aria-label="Dismiss message">×</button>
        </div>
      )}

      <main className={result ? "layout has-result" : "layout"}>
        <section className="card" aria-labelledby="listing-heading">
          <h2 id="listing-heading">Listing details</h2>
          <form onSubmit={submit} noValidate>
            <label htmlFor="title">Listing title</label>
            <input
              id="title"
              value={form.title}
              onChange={field("title")}
              placeholder="e.g. Leather laptop backpack, black"
              maxLength={200}
              required
            />

            <div className="field-grid">
              <div>
                <label htmlFor="brand">Brand</label>
                <input id="brand" value={form.brand} onChange={field("brand")} maxLength={120} />
              </div>
              <div>
                <label htmlFor="category">Category</label>
                <input id="category" value={form.category} onChange={field("category")} placeholder="e.g. Backpack" maxLength={120} />
              </div>
              <div>
                <label htmlFor="color">Color</label>
                <input id="color" value={form.color} onChange={field("color")} maxLength={120} />
              </div>
              <div>
                <label htmlFor="model">Model</label>
                <input id="model" value={form.model} onChange={field("model")} maxLength={120} />
              </div>
            </div>

            <label htmlFor="description">Description</label>
            <textarea
              id="description"
              value={form.description}
              onChange={field("description")}
              placeholder="Material, dimensions, condition and anything else the buyer should know."
              maxLength={5000}
            />
            <button type="button" className="light" onClick={listen} disabled={listening}>
              {listening ? "🎙 Listening…" : "🎙 Add description by voice"}
            </button>

            <div className="photo-head">
              <span className="label">Product photos ({files.length}/{MAX_IMAGES})</span>
              <span className="hint">Good light, whole product, no filters</span>
            </div>
            <div className="photo-actions">
              <button type="button" className="light" onClick={() => cameraRef.current?.click()}>
                📷 Take photo
              </button>
              <button type="button" className="light" onClick={() => galleryRef.current?.click()}>
                🖼 Choose photos
              </button>
              <input
                ref={cameraRef}
                type="file"
                accept="image/*"
                capture="environment"
                className="visually-hidden"
                tabIndex={-1}
                aria-hidden="true"
                onChange={(event) => { addFiles(event.target.files); event.target.value = ""; }}
              />
              <input
                ref={galleryRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                multiple
                className="visually-hidden"
                tabIndex={-1}
                aria-hidden="true"
                onChange={(event) => { addFiles(event.target.files); event.target.value = ""; }}
              />
            </div>

            {previews.length > 0 && (
              <ul className="thumbs">
                {previews.map((src, index) => (
                  <li key={src}>
                    <img src={src} alt={`Selected product photo ${index + 1}`} />
                    <button type="button" onClick={() => removeFile(index)} aria-label={`Remove photo ${index + 1}`}>×</button>
                  </li>
                ))}
              </ul>
            )}

            <button type="submit" className="primary" disabled={busy}>
              {busy ? "Analyzing your listing…" : "Run AI verification"}
            </button>
            <p className="fineprint">Analysis is advisory. Never share personal or payment information in the description.</p>
          </form>
        </section>

        {result ? (
          <Report result={result} onSpeak={speak} onReset={reset} />
        ) : (
          <section className="card how">
            <h2>What gets checked</h2>
            <ul>
              <li><b>Text ↔ image match</b> — do the photos support the title and description?</li>
              <li><b>Image quality</b> — blur, resolution and product framing.</li>
              <li><b>Attributes</b> — brand, model, colour and product type seen in the photos.</li>
              <li><b>Duplicates</b> — whether the same photos appeared in another listing.</li>
              <li><b>Completeness</b> — whether the claimed product is actually visible.</li>
            </ul>
            <p className="fineprint">
              Reports are generated from measured signals. Duplicate and manipulation checks are
              heuristics, not proof of wrongdoing.
            </p>
          </section>
        )}
      </main>

      <footer>ProductProof AI · Seller Portal · {new Date().getFullYear()}</footer>
    </div>
  );
}

function Report({ result, onSpeak, onReset }) {
  const decision = DECISION[result.decision] ? result.decision : "REVIEW";
  const info = DECISION[decision];
  const score = Math.round(result.correctness_score || 0);
  const attributes = result.attributes || [];
  const checks = result.quality_checks || [];
  const summary = result.llm_report?.final_explanation || result.explanation;
  const ocr = (result.ocr_text || []).flat();

  return (
    <section className={`card report ${decision.toLowerCase()}`} aria-labelledby="report-heading">
      <div className="decision">
        <span className="badge">{decision}</span>
        <div>
          <h2 id="report-heading">{info.title}</h2>
          <p>{info.detail}</p>
        </div>
      </div>

      <div className="stats">
        <div>
          <b>{score}<small>/100</small></b>
          <small>Correctness score</small>
        </div>
        <div>
          <b>{result.text_image_match_pct == null ? "—" : `${Math.round(result.text_image_match_pct)}%`}</b>
          <small>Text ↔ image match</small>
        </div>
        <div>
          <b>{result.image_quality_pct == null ? "—" : `${Math.round(result.image_quality_pct)}%`}</b>
          <small>Image quality</small>
        </div>
        <div>
          <b>{Math.round((result.confidence || 0) * 100)}%</b>
          <small>Confidence</small>
        </div>
      </div>

      {summary && <p className="summary">{summary}</p>}

      {result.mismatches?.length > 0 && (
        <div className="issues">
          <h3>Conflicting details</h3>
          <ul>{result.mismatches.map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
      )}

      {attributes.length > 0 && (
        <>
          <h3>Attribute findings</h3>
          <ul className="chips">
            {attributes.map((attribute) => (
              <li key={attribute.attribute} className={`chip ${String(attribute.status || "UNKNOWN").toLowerCase()}`}>
                <b>{attribute.attribute}</b>
                <span>{attribute.detected || attribute.expected || "not visible"}</span>
                <small>{attribute.status}</small>
              </li>
            ))}
          </ul>
        </>
      )}

      {checks.length > 0 && (
        <>
          <h3>Image checks</h3>
          <ul className="checks">
            {checks.map((check) => (
              <li key={check.label} className={check.passed ? "pass" : "fail"}>
                <span aria-hidden="true">{check.passed ? "✓" : "✕"}</span>
                <div><b>{check.label}</b><small>{check.detail}</small></div>
              </li>
            ))}
          </ul>
        </>
      )}

      {ocr.length > 0 && (
        <p className="fineprint"><b>Text visible in photos:</b> {ocr.join(", ")}</p>
      )}

      {result.persisted === false && (
        <p className="fineprint">
          This report was not saved because marketplace storage is not configured. Save a copy if you
          need it later.
        </p>
      )}

      <div className="report-actions">
        <button type="button" className="light" onClick={onSpeak}>🔊 Read report aloud</button>
        <button type="button" className="primary" onClick={onReset}>Check another listing</button>
      </div>
    </section>
  );
}

createRoot(document.getElementById("root")).render(<App />);
