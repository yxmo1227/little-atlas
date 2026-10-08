import assert from 'node:assert/strict';
import { randomBytes } from 'node:crypto';
import test from 'node:test';

const base = process.env.ATLAS_TEST_URL;

test('notebook headings and edits sync between sessions without overwriting newer work', { skip: !base }, async (t) => {
  const origin = new URL(base).origin;
  const password = randomBytes(24).toString('base64url');
  const email = `atlas-notebook-${randomBytes(10).toString('hex')}@example.invalid`;
  const otherEmail = `atlas-private-${randomBytes(10).toString('hex')}@example.invalid`;
  const accounts = [];

  async function request(cookie, path, body, method = body === undefined ? 'GET' : 'POST') {
    const response = await fetch(origin + path, {
      method, headers: { origin, ...(cookie ? { cookie } : {}), ...(body === undefined ? {} : { 'content-type': 'application/json' }) },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const raw = await response.text();
    assert.match(response.headers.get('content-type') ?? '', /application\/json/, `${method} ${path}: ${response.status} ${raw.slice(0, 100)}`);
    return { status: response.status, data: JSON.parse(raw), response };
  }
  const sessionCookie = (response) => response.headers.getSetCookie().map(value => value.split(';')[0]).join('; ');
  t.after(async () => {
    for (const cookie of accounts) {
      const removed = await request(cookie, '/api/auth/delete-user', { password });
      assert.equal(removed.status, 200, 'Remove only the disposable diagnostic account');
    }
  });

  const signup = await request('', '/api/auth/sign-up/email', { email, password, name: 'Notebook check' });
  assert.equal(signup.status, 200, signup.data.message);
  const firstSession = sessionCookie(signup.response); accounts.push(firstSession);
  const created = await request(firstSession, '/api/entries', { content: 'Code messages describe status and errors.' });
  assert.equal(created.status, 201);
  const original = created.data.entry;
  assert.ok(original.title && original.category, 'Content automatically produces metadata');
  assert.ok(original.blocks.length, 'Plain content becomes an editable document');
  const blocks = [
    { id: 'overview', type: 'heading1', text: 'Message formats' },
    { id: 'formats', type: 'paragraph', text: 'A status message can include a code and a description.' },
    { id: 'errors', type: 'heading1', text: 'Error handling' },
    { id: 'retry', type: 'heading2', text: 'Retry messages' },
    { id: 'details', type: 'paragraph', text: 'Keep retry messages clear.' },
  ];
  const edited = await request(firstSession, `/api/entries/${original.id}`, {
    blocks, title: 'Code message notebook', category: 'Technology', subcategory: 'Developer notes', baseRevision: original.revision,
  }, 'PATCH');
  assert.equal(edited.status, 200);
  assert.deepEqual(edited.data.entry.blocks, blocks);
  assert.equal(edited.data.entry.content, blocks.map(block => block.text).join('\n\n'));
  assert.ok(edited.data.entry.revision > original.revision);

  const login = await request('', '/api/auth/sign-in/email', { email, password });
  assert.equal(login.status, 200);
  const secondSession = sessionCookie(login.response);
  const loaded = await request(secondSession, `/api/entries/${original.id}`);
  assert.equal(loaded.status, 200);
  assert.deepEqual(loaded.data.entry.blocks, blocks, 'Another signed-in device reads the same headings and content');
  const nextBlocks = [...blocks.filter(block => block.id !== 'details'), { id: 'next', type: 'paragraph', text: 'Revised on a second device.' }];
  const secondEdit = await request(secondSession, `/api/entries/${original.id}`, { blocks: nextBlocks, baseRevision: loaded.data.entry.revision }, 'PATCH');
  assert.equal(secondEdit.status, 200);
  assert.equal(secondEdit.data.entry.title, 'Code message notebook', 'Later edits keep the customized title');
  assert.equal(secondEdit.data.entry.category, 'Technology', 'Later edits keep the customized classification');
  const stale = await request(firstSession, `/api/entries/${original.id}`, { content: 'An old browser draft.', baseRevision: edited.data.entry.revision }, 'PATCH');
  assert.equal(stale.status, 409, 'A stale device must not silently replace newer work');
  assert.equal(stale.data.code, 'CONFLICT');
  const confirmed = await request(firstSession, `/api/entries/${original.id}`);
  assert.deepEqual(confirmed.data.entry.blocks, nextBlocks);

  const large = await request(firstSession, '/api/entries', { content: 'Long article notes.\n\n' + 'A detailed notebook paragraph. '.repeat(1500) });
  assert.equal(large.status, 201, 'Articles can exceed the old 30,000-character entry limit');

  const otherSignup = await request('', '/api/auth/sign-up/email', { email: otherEmail, password, name: 'Private check' });
  assert.equal(otherSignup.status, 200, otherSignup.data.message);
  const foreign = sessionCookie(otherSignup.response); accounts.push(foreign);
  assert.equal((await request(foreign, `/api/entries/${original.id}`)).status, 404);
  assert.equal((await request(foreign, `/api/entries/${original.id}`, { content: 'A different account.' }, 'PATCH')).status, 404);
  assert.deepEqual((await request(foreign, '/api/entries')).data.entries, [], 'A new account has a private empty notebook');
});
