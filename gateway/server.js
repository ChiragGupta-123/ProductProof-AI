const express = require("express");
const cors = require("cors");
const multer = require("multer");

const DEFAULT_UPSTREAM = "http://127.0.0.1:8000";
const DEFAULT_ORIGINS = [
  "http://localhost:3000",
  "http://127.0.0.1:3000",
  "http://localhost:5173",
  "http://127.0.0.1:5173",
];
const MAX_IMAGE_MB = Number(process.env.MAX_IMAGE_MB || 10);
const MAX_IMAGES = Number(process.env.MAX_IMAGES || 8);
const UPSTREAM_TIMEOUT_MS = Number(process.env.UPSTREAM_TIMEOUT_MS || 180000);
const VERIFY_FIELDS = ["title", "description", "brand", "category", "color", "model", "sku"];

function allowedOrigins() {
  const configured = process.env.ALLOWED_ORIGINS;
  const list = configured ? configured.split(",") : DEFAULT_ORIGINS;
  return list.map((origin) => origin.trim().replace(/\/+$/, "")).filter(Boolean);
}

function isLoopbackOrigin(origin) {
  try {
    const url = new URL(origin);
    return (
      ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname) &&
      (url.protocol === "http:" || url.protocol === "https:")
    );
  } catch {
    return false;
  }
}

function upstreamError(res, error) {
  const timedOut = error && (error.name === "TimeoutError" || error.name === "AbortError");
  if (timedOut) {
    return res.status(504).json({
      error: "The verification service did not respond in time. Please retry.",
    });
  }
  return res.status(502).json({
    error: "The verification service is unavailable.",
    detail: error ? String(error.message || error) : undefined,
  });
}

function createApp(options = {}) {
  const upstreamUrl = (options.upstreamUrl || process.env.FASTAPI_URL || DEFAULT_UPSTREAM)
    .replace(/\/+$/, "");
  const fetchImpl = options.fetchImpl || globalThis.fetch;
  const app = express();
  const origins = allowedOrigins();
  // Dev servers can pick any free port; allow loopback in development only.
  // Production is locked to ALLOWED_ORIGINS (or the documented defaults).
  const allowLoopback = process.env.NODE_ENV !== "production";
  const upload = multer({
    storage: multer.memoryStorage(),
    limits: { fileSize: MAX_IMAGE_MB * 1024 * 1024, files: MAX_IMAGES },
  });

  app.disable("x-powered-by");
  app.use(
    cors({
      origin(origin, callback) {
        // Allow same-origin/server-to-server calls (no Origin header) and the
        // configured browser clients; never reflect arbitrary origins.
        const normalized = origin ? origin.replace(/\/+$/, "") : origin;
        if (
          !origin ||
          origins.includes(normalized) ||
          (allowLoopback && isLoopbackOrigin(normalized))
        ) {
          return callback(null, true);
        }
        const error = new Error(`Origin ${origin} is not allowed`);
        error.code = "ERR_CORS";
        return callback(error);
      },
      credentials: true,
      methods: ["GET", "POST", "OPTIONS"],
    })
  );
  app.use(express.json({ limit: "2mb" }));

  app.get("/health", async (_req, res) => {
    try {
      const response = await fetchImpl(`${upstreamUrl}/api/v1/health`, {
        signal: AbortSignal.timeout(10000),
      });
      const body = await response.json();
      res.status(response.status).json({ gateway: "up", ...body });
    } catch (error) {
      res.status(503).json({
        gateway: "up",
        status: "upstream-down",
        error: String(error.message || error),
      });
    }
  });

  // IMPORTANT: this route must be registered before the /api proxy below.
  // Previously the catch-all matched first and rejected every multipart
  // request, making the product's main flow unreachable through the gateway.
  app.post("/api/v1/verify", (req, res) => {
    upload.array("images", MAX_IMAGES)(req, res, async (uploadError) => {
      if (uploadError) {
        const status = uploadError.code === "LIMIT_FILE_SIZE" ? 413 : 400;
        const message =
          uploadError.code === "LIMIT_FILE_SIZE"
            ? `Each image must be ${MAX_IMAGE_MB} MB or smaller.`
            : uploadError.code === "LIMIT_FILE_COUNT" ||
              uploadError.code === "LIMIT_UNEXPECTED_FILE"
            ? `Maximum ${MAX_IMAGES} images per verification.`
            : uploadError.message;
        return res.status(status).json({ error: message });
      }
      if (!req.files || req.files.length === 0) {
        return res.status(400).json({ error: "At least one image is required." });
      }
      try {
        const form = new FormData();
        for (const field of VERIFY_FIELDS) {
          form.append(field, req.body[field] || "");
        }
        for (const file of req.files) {
          form.append(
            "images",
            new Blob([file.buffer], { type: file.mimetype }),
            file.originalname || "image.jpg"
          );
        }
        const response = await fetchImpl(`${upstreamUrl}/api/v1/verify`, {
          method: "POST",
          body: form,
          signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
        });
        const text = await response.text();
        res
          .status(response.status)
          .type(response.headers.get("content-type") || "application/json")
          .send(text);
      } catch (error) {
        upstreamError(res, error);
      }
    });
  });

  app.use("/api", async (req, res) => {
    if ((req.headers["content-type"] || "").includes("multipart/form-data")) {
      return res.status(415).json({
        error: "Multipart uploads are only supported on POST /api/v1/verify.",
      });
    }
    const target = `${upstreamUrl}/api${req.originalUrl.replace(/^\/api/, "")}`;
    try {
      const headers = {};
      let body;
      if (!["GET", "HEAD"].includes(req.method)) {
        headers["content-type"] = "application/json";
        body = JSON.stringify(req.body ?? {});
      }
      const response = await fetchImpl(target, {
        method: req.method,
        headers,
        body,
        signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
      });
      const text = await response.text();
      res
        .status(response.status)
        .type(response.headers.get("content-type") || "application/json")
        .send(text);
    } catch (error) {
      upstreamError(res, error);
    }
  });

  app.use((_req, res) => res.status(404).json({ error: "Not found" }));

  // eslint-disable-next-line no-unused-vars
  app.use((error, _req, res, _next) => {
    const status = error && error.code === "ERR_CORS" ? 403 : 500;
    res.status(status).json({ error: error.message || "Unexpected gateway error" });
  });

  return app;
}

function resolvePort() {
  const parsed = Number.parseInt(process.env.PORT ?? "", 10);
  return Number.isInteger(parsed) && parsed > 0 && parsed <= 65535 ? parsed : 4000;
}

if (require.main === module) {
  const port = resolvePort();
  const upstream = (process.env.FASTAPI_URL || DEFAULT_UPSTREAM).replace(/\/+$/, "");
  createApp().listen(port, () => {
    console.log(`ProductProof Express gateway on http://localhost:${port} -> ${upstream}`);
  });
}

module.exports = { createApp };
