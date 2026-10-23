const test = require("node:test");
const assert = require("node:assert/strict");
const http = require("node:http");
const { createApp } = require("../server");

function startFakeUpstream() {
  const received = { verifyBodies: [], jsonBodies: [] };
  const server = http.createServer((req, res) => {
    const chunks = [];
    req.on("data", (chunk) => chunks.push(chunk));
    req.on("end", () => {
      const body = Buffer.concat(chunks);
      if (req.url === "/api/v1/health") {
        res.writeHead(200, { "content-type": "application/json" });
        return res.end(JSON.stringify({ status: "ok", mongodb: "unavailable" }));
      }
      if (req.method === "POST" && req.url === "/api/v1/verify") {
        received.verifyBodies.push({
          contentType: req.headers["content-type"] || "",
          text: body.toString("latin1"),
        });
        res.writeHead(200, { "content-type": "application/json" });
        return res.end(JSON.stringify({ review_id: "test-review", decision: "REVIEW" }));
      }
      if (req.method === "GET" && req.url === "/api/v1/reviews") {
        res.writeHead(200, { "content-type": "application/json" });
        return res.end(JSON.stringify([{ id: "abc", title: "Sample" }]));
      }
      if (req.method === "POST" && req.url === "/api/v1/reviews/abc") {
        received.jsonBodies.push(body.toString("utf8"));
        res.writeHead(200, { "content-type": "application/json" });
        return res.end(JSON.stringify({ status: "updated" }));
      }
      res.writeHead(404, { "content-type": "application/json" });
      res.end(JSON.stringify({ error: "upstream 404" }));
    });
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      resolve({ server, port, received });
    });
  });
}

async function withGateway(run) {
  const upstream = await startFakeUpstream();
  const app = createApp({ upstreamUrl: `http://127.0.0.1:${upstream.port}` });
  const server = app.listen(0, "127.0.0.1");
  await new Promise((resolve) => server.once("listening", resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  try {
    await run(base, upstream.received);
  } finally {
    await new Promise((resolve) => server.close(resolve));
    await new Promise((resolve) => upstream.server.close(resolve));
  }
}

function verifyForm() {
  const form = new FormData();
  form.append("title", "Leather jacket");
  form.append("brand", "Acme");
  form.append("images", new Blob([Buffer.from("fake-image-1")], { type: "image/jpeg" }), "one.jpg");
  form.append("images", new Blob([Buffer.from("fake-image-2")], { type: "image/png" }), "two.png");
  return form;
}

test("multipart verification reaches the upstream service", async () => {
  await withGateway(async (base, received) => {
    const response = await fetch(`${base}/api/v1/verify`, {
      method: "POST",
      body: verifyForm(),
    });
    assert.equal(response.status, 200);
    const body = await response.json();
    assert.equal(body.review_id, "test-review");
    assert.equal(received.verifyBodies.length, 1);
    const forwarded = received.verifyBodies[0];
    assert.match(forwarded.contentType, /multipart\/form-data/);
    assert.equal((forwarded.text.match(/name="images"/g) || []).length, 2);
    assert.match(forwarded.text, /Leather jacket/);
  });
});

test("JSON requests are proxied to the upstream API", async () => {
  await withGateway(async (base, received) => {
    const list = await fetch(`${base}/api/v1/reviews`);
    assert.equal(list.status, 200);
    assert.deepEqual(await list.json(), [{ id: "abc", title: "Sample" }]);

    const update = await fetch(`${base}/api/v1/reviews/abc`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ decision: "APPROVE", reviewer_note: "ok" }),
    });
    assert.equal(update.status, 200);
    assert.match(received.jsonBodies[0], /APPROVE/);
  });
});

test("verification requires at least one image", async () => {
  await withGateway(async (base) => {
    const form = new FormData();
    form.append("title", "No photos");
    const response = await fetch(`${base}/api/v1/verify`, { method: "POST", body: form });
    assert.equal(response.status, 400);
    assert.match((await response.json()).error, /image/i);
  });
});

test("multipart uploads are rejected outside the verify endpoint", async () => {
  await withGateway(async (base) => {
    const response = await fetch(`${base}/api/v1/reviews/abc`, {
      method: "POST",
      body: verifyForm(),
    });
    assert.equal(response.status, 415);
  });
});

test("loopback dev servers on any port are allowed", async () => {
  await withGateway(async (base) => {
    const response = await fetch(`${base}/api/v1/reviews`, {
      headers: { origin: "http://127.0.0.1:53413" },
    });
    assert.equal(response.status, 200);
  });
});

test("disallowed browser origins are rejected", async () => {
  await withGateway(async (base) => {
    const response = await fetch(`${base}/api/v1/reviews`, {
      headers: { origin: "https://evil.example.com" },
    });
    assert.equal(response.status, 403);
  });
});

test("health reports the gateway and upstream state", async () => {
  await withGateway(async (base) => {
    const response = await fetch(`${base}/health`);
    assert.equal(response.status, 200);
    const body = await response.json();
    assert.equal(body.gateway, "up");
    assert.equal(body.status, "ok");
  });
});
