import assert from "node:assert/strict";
import { randomBytes } from "node:crypto";
import test from "node:test";

const baseURL = process.env.ATLAS_TEST_URL;

test("email accounts validate sessions and keep dictionaries private", { skip: !baseURL }, async (t) => {
  const origin = new URL(baseURL).origin;
  const password = randomBytes(24).toString("base64url");
  const email = `atlas-check-${randomBytes(10).toString("hex")}@example.invalid`;
  const otherEmail = `atlas-check-${randomBytes(10).toString("hex")}@example.invalid`;
  const testIP = `192.0.2.${1 + (randomBytes(1)[0] % 254)}`;
  const remainingAccounts = new Map();
  let cookie = "";

  t.after(async () => {
    for (const [accountEmail, accountCookie] of remainingAccounts) {
      cookie = accountCookie;
      let removal = await request("/api/auth/delete-user", "POST", { password });
      if (removal.response.status === 401) {
        cookie = "";
        const login = await request("/api/auth/sign-in/email", "POST", { email: accountEmail, password });
        assert.equal(login.response.status, 200, "Could not restore a diagnostic session for cleanup");
        rememberSession(login.response, accountEmail);
        removal = await request("/api/auth/delete-user", "POST", { password });
      }
      assert.equal(removal.response.status, 200, "Could not remove a diagnostic account");
      remainingAccounts.delete(accountEmail);
    }
  });

  async function request(path, method = "GET", body, override = {}) {
    const response = await fetch(`${origin}${path}`, {
      method,
      headers: {
        origin,
        "cf-connecting-ip": testIP,
        ...(cookie ? { cookie } : {}),
        ...(body !== undefined ? { "content-type": "application/json" } : {}),
        ...override,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      redirect: "manual",
    });
    const text = await response.text();
    let result;
    try { result = JSON.parse(text); }
    catch { result = { message: text.slice(0, 200) }; }
    return { response, result };
  }

  function rememberSession(response, accountEmail) {
    const cookies = response.headers.getSetCookie();
    cookie = cookies.map((value) => value.split(";")[0]).join("; ");
    remainingAccounts.set(accountEmail, cookie);
    assert.ok(cookies.some((value) => /httponly/i.test(value)), "Session cookie must be HTTP-only");
    assert.ok(cookies.some((value) => /samesite=lax/i.test(value)), "Session cookie must be SameSite=Lax");
    if (origin.startsWith("https:")) {
      assert.ok(cookies.some((value) => /secure/i.test(value)), "HTTPS session cookie must be Secure");
    }
  }

  const anonymous = await request("/api/entries");
  assert.equal(anonymous.response.status, 401);

  const weak = await request("/api/auth/sign-up/email", "POST", { email, password: "short", name: "Test account" });
  assert.equal(weak.response.status, 400);

  const signedUp = await request("/api/auth/sign-up/email", "POST", { email, password, name: "Test account" });
  assert.equal(signedUp.response.status, 200, signedUp.result?.message);
  rememberSession(signedUp.response, email);
  const ownSession = await request("/api/auth/get-session");
  assert.equal(ownSession.result.user.email, email);
  const empty = await request("/api/entries");
  assert.equal(empty.response.status, 200);
  assert.deepEqual(empty.result.entries, []);

  const crossOriginSave = await request("/api/entries", "POST", { content: "This must not be saved." }, { origin: "https://unrelated.example" });
  assert.equal(crossOriginSave.response.status, 403);

  const created = await request("/api/entries", "POST", { content: "Erebus personifies darkness in Greek mythology." });
  assert.equal(created.response.status, 201, created.result?.error);
  assert.ok(created.result.entry.title);
  assert.ok(created.result.entry.category);
  const entryId = created.result.entry.id;
  const firstCookie = cookie;

  const signedOut = await request("/api/auth/sign-out", "POST", {});
  assert.equal(signedOut.response.status, 200);
  cookie = "";
  const revoked = await request("/api/auth/get-session", "GET", undefined, { cookie: firstCookie });
  assert.equal(revoked.result, null, "Signing out must revoke the database session");

  const wrong = await request("/api/auth/sign-in/email", "POST", { email, password: `${password}wrong` });
  assert.equal(wrong.response.status, 401);

  const second = await request("/api/auth/sign-up/email", "POST", { email: otherEmail, password, name: "Second account" });
  assert.equal(second.response.status, 200, second.result?.message);
  rememberSession(second.response, otherEmail);
  const otherDictionary = await request("/api/entries");
  assert.deepEqual(otherDictionary.result.entries, []);
  const otherEdit = await request(`/api/entries/${entryId}`, "PATCH", { content: "Unwanted change" });
  assert.equal(otherEdit.response.status, 404);
  const otherDelete = await request(`/api/entries/${entryId}`, "DELETE");
  assert.equal(otherDelete.response.status, 404);
  const removedSecond = await request("/api/auth/delete-user", "POST", { password });
  assert.equal(removedSecond.response.status, 200, removedSecond.result?.message);
  remainingAccounts.delete(otherEmail);
  const removedSecondSession = await request("/api/auth/get-session");
  assert.equal(removedSecondSession.result, null, "Deleting an account must revoke its session");
  cookie = "";
  const removedSecondLogin = await request("/api/auth/sign-in/email", "POST", { email: otherEmail, password });
  assert.equal(removedSecondLogin.response.status, 401, "A deleted account must not sign in");

  const csrf = await request("/api/auth/sign-in/email", "POST", { email, password }, { origin: "https://unrelated.example" });
  assert.equal(csrf.response.status, 403);
  const signedIn = await request("/api/auth/sign-in/email", "POST", { email, password });
  assert.equal(signedIn.response.status, 200, signedIn.result?.message);
  rememberSession(signedIn.response, email);
  const researched = await request(`/api/research?q=${encodeURIComponent("厄瑞波斯")}`);
  assert.equal(researched.response.status, 200);
  assert.equal(researched.result.error, undefined, researched.result.error);
  assert.equal(researched.result.title, "Erebus");
  assert.equal(new URL(researched.result.sourceUrl).hostname, "en.wikipedia.org");
  assert.ok(Array.isArray(researched.result.facts) && researched.result.facts.length > 0);
  assert.match(researched.result.facts.map((fact) => fact.text).join(" "), /\b(?:Erebus|darkness|Greek|deity|primordial)\b/i);
  for (const fact of researched.result.facts) {
    assert.equal(typeof fact.text, "string");
    assert.ok(!/[\u3400-\u9fff]/u.test(fact.text), "Research passages must be in English");
    assert.equal(new URL(fact.sourceUrl).protocol, "https:");
    assert.equal(new URL(fact.sourceUrl).hostname, "en.wikipedia.org");
  }
  const saved = await request("/api/entries");
  assert.equal(saved.result.entries.length, 1);
  assert.equal(saved.result.entries[0].id, entryId);
  const deleted = await request(`/api/entries/${entryId}`, "DELETE");
  assert.equal(deleted.response.status, 200);
  const removedFirst = await request("/api/auth/delete-user", "POST", { password });
  assert.equal(removedFirst.response.status, 200, removedFirst.result?.message);
  remainingAccounts.delete(email);
  const removedFirstSession = await request("/api/auth/get-session");
  assert.equal(removedFirstSession.result, null, "Deleting an account must revoke its session");
  cookie = "";
  const removedFirstLogin = await request("/api/auth/sign-in/email", "POST", { email, password });
  assert.equal(removedFirstLogin.response.status, 401, "A deleted account must not sign in");
});
