import test from "node:test";
import assert from "node:assert/strict";
import { researchTopic, researchUrl } from "../lib/knowledge.ts";

const dns = () => new Response(JSON.stringify({ Status: 0, Answer: [{ type: 1, data: "93.184.216.34" }] }), { headers: { "content-type": "application/json" } });
const html = (body, headers = {}) => new Response(body, { headers: { "content-type": "text/html; charset=utf-8", ...headers } });

test("pasted article URLs import original text without scripts or navigation", async (context) => {
  context.mock.method(globalThis, "fetch", async (input) => {
    const url = new URL(input);
    if (url.hostname === "cloudflare-dns.com") return dns();
    return html(`<html><head><title>Erebus – Wikipedia</title><script><p>This false script paragraph must never appear as article content.</p></script></head><body>
      <nav><p>Browse all of the pages and click these menu items for more information.</p></nav>
      <article><h1>Erebus</h1><p>In Greek mythology, <b>Erebus</b> is the personification of darkness.</p>
      <h2>Family</h2><p>According to Hesiod, he is an offspring of Chaos &amp; the father of Aether.</p>
      <p>According to Hesiod, he is an offspring of Chaos &amp; the father of Aether.</p></article>
      <footer><p>Please sign in to your account to continue browsing our website today.</p></footer></body></html>`);
  });
  const result = await researchTopic("https://article.example.com/erebus#family");
  assert.equal(result.title, "Erebus");
  assert.equal(result.category, "Myths & Beliefs");
  assert.equal(result.facts.length, 2);
  assert.equal(result.facts[1].section, "Family");
  assert.match(result.facts[1].text, /Chaos & the father/);
  assert.ok(result.facts.every((fact) => fact.sourceUrl === "https://article.example.com/erebus"));
});

test("private, malformed, credential, insecure, and search-result URLs are rejected", async (context) => {
  let requests = 0;
  context.mock.method(globalThis, "fetch", async () => { requests++; return dns(); });
  for (const url of ["not a URL", "http://example.com/article", "https://localhost/article", "https://127.0.0.1/article", "https://2130706433/article", "https://10.0.0.8/article", "https://[::1]/article", "https://[fd00::1]/article", "https://user:password@example.com/article", "https://example.com:8443/article", "https://www.google.com/search?q=erebus"]) {
    assert.ok((await researchUrl(url)).error, url);
  }
  assert.equal(requests, 0);
});

test("hostnames resolving privately are also rejected", async (context) => {
  context.mock.method(globalThis, "fetch", async () => new Response(JSON.stringify({ Status: 0, Answer: [{ type: 1, data: "192.168.1.8" }] })));
  const result = await researchUrl("https://internal-address.example.com/article");
  assert.match(result.error, /Only public/);
  assert.deepEqual(result.facts, []);
});

test("public redirects preserve the final original URL as attribution", async (context) => {
  context.mock.method(globalThis, "fetch", async (input) => {
    const url = new URL(input);
    if (url.hostname === "cloudflare-dns.com") return dns();
    if (url.pathname === "/old") return new Response(null, { status: 302, headers: { location: "/article" } });
    return html("<title>Photosynthesis</title><p>Photosynthesis lets plants transform sunlight into stored chemical energy.</p>");
  });
  const result = await researchUrl("https://redirect.example.com/old");
  assert.equal(result.sourceUrl, "https://redirect.example.com/article");
  assert.equal(result.category, "Nature & Life");
  assert.equal(result.facts.length, 1);
});

test("redirects to private addresses are never fetched", async (context) => {
  let articleFetches = 0;
  context.mock.method(globalThis, "fetch", async (input) => {
    if (new URL(input).hostname === "cloudflare-dns.com") return dns();
    articleFetches++;
    return new Response(null, { status: 302, headers: { location: "https://127.0.0.1/private" } });
  });
  assert.match((await researchUrl("https://private-redirect.example.com/article")).error, /Only public/);
  assert.equal(articleFetches, 1);
});

test("large, protected, non-HTML, and unreadable pages give clear errors", async (context) => {
  const cases = [
    ["large", () => html("<p>short</p>", { "content-length": "500001" }), /too large/],
    ["protected", () => new Response("Login", { status: 403 }), /requires access/],
    ["download", () => new Response("PDF", { headers: { "content-type": "application/pdf" } }), /rather than a download/],
    ["unreadable", () => html("<script>document.write('content')</script><p>只有中文，不应凭空翻译成英文或生成事实。</p>"), /no readable English/],
  ];
  for (const [name, response, error] of cases) {
    context.mock.method(globalThis, "fetch", async (input) => new URL(input).hostname === "cloudflare-dns.com" ? dns() : response());
    assert.match((await researchUrl(`https://${name}.example.com/article`)).error, error);
    context.mock.restoreAll();
  }
});

test("network failures return an empty result without invented content", async (context) => {
  context.mock.method(globalThis, "fetch", async () => { throw new TypeError("fetch failed"); });
  const result = await researchUrl("https://offline.example.com/article");
  assert.match(result.error, /Could not reach this article/);
  assert.deepEqual(result.facts, []);
});

test("excessively nested malformed markup is bounded", async (context) => {
  context.mock.method(globalThis, "fetch", async (input) => new URL(input).hostname === "cloudflare-dns.com" ? dns() : html("<div>".repeat(200) + "<p>An English paragraph could otherwise be present inside broken markup.</p>"));
  assert.match((await researchUrl("https://broken-markup.example.com/article")).error, /markup could not be read/);
});
