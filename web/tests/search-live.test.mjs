import assert from 'node:assert/strict';
import { randomBytes } from 'node:crypto';
import test from 'node:test';

const base = process.env.ATLAS_TEST_URL;

test('Chinese broad search finds English topics and canonical currency names open the correct article', { skip: !base }, async (t) => {
  const origin = new URL(base).origin;
  const password = randomBytes(24).toString('base64url');
  const email = `atlas-search-${randomBytes(10).toString('hex')}@example.invalid`;
  let cookie = '';
  async function request(path, body) {
    const response = await fetch(origin + path, {
      method: 'POST', headers: { origin, 'content-type': 'application/json', ...(cookie ? { cookie } : {}) }, body: JSON.stringify(body),
    });
    assert.match(response.headers.get('content-type') ?? '', /application\/json/);
    return { status: response.status, data: await response.json(), response };
  }
  assert.equal((await request('/api/research', { content: '加密市场' })).status, 401);
  const signup = await request('/api/auth/sign-up/email', { email, password, name: 'Search check' });
  assert.equal(signup.status, 200, signup.data.message);
  cookie = signup.response.headers.getSetCookie().map(value => value.split(';')[0]).join('; ');
  t.after(async () => {
    assert.equal((await request('/api/auth/delete-user', { password })).status, 200, 'Remove only this disposable diagnostic account');
  });
  const broad = await request('/api/research', { content: '加密市场' });
  assert.equal(broad.status, 200);
  assert.equal(broad.data.error, undefined, broad.data.error);
  const cryptocurrency = broad.data.candidates?.find(candidate => candidate.title === 'Cryptocurrency');
  assert.ok(cryptocurrency, 'A broad Chinese query must return its relevant English article');
  assert.ok(cryptocurrency.snippet.length > 30);
  assert.ok(!/[\u3400-\u9fff]/.test(cryptocurrency.snippet), 'Research results remain in English');
  assert.equal(new URL(cryptocurrency.sourceUrl).hostname, 'en.wikipedia.org');
  const selected = await request('/api/research', { content: cryptocurrency.title, exactTitle: true });
  assert.equal(selected.status, 200);
  assert.equal(selected.data.title, 'Cryptocurrency');
  assert.equal(selected.data.error, undefined, selected.data.error);
  assert.ok(selected.data.facts.length > 5);
  assert.ok(selected.data.images.length > 0);
  const canonical = await request('/api/research', { content: '加密货币' });
  assert.equal(canonical.status, 200);
  assert.equal(canonical.data.title, 'Cryptocurrency', 'Chinese character variants must not select an unrelated stadium');
  assert.ok(canonical.data.facts.length > 5);
  const english = await request('/api/research', { content: 'crypto market' });
  assert.equal(english.status, 200);
  assert.equal(english.data.error, undefined, english.data.error);
  assert.ok(english.data.candidates?.some(candidate => candidate.title === 'Cryptocurrency'));
  const dottedTitle = await request('/api/research', { content: 'Crypto.com', exactTitle: true });
  assert.equal(dottedTitle.status, 200);
  assert.equal(dottedTitle.data.title, 'Crypto.com', 'A selected reference title must not be parsed as a sentence');
  assert.equal(dottedTitle.data.error, undefined, dottedTitle.data.error);
  assert.ok(dottedTitle.data.facts.length > 0);
  const typedTitle = await request('/api/research', { content: 'Crypto.com is a cryptocurrency exchange.' });
  assert.equal(typedTitle.status, 200);
  assert.equal(typedTitle.data.title, 'Crypto.com');
  assert.equal(typedTitle.data.error, undefined, typedTitle.data.error);
  assert.equal((await request('/api/research', { content: 'Cryptocurrency', exactTitle: 'true' })).status, 400);
});
