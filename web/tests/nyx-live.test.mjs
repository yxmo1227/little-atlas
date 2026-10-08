import assert from 'node:assert/strict';
import { randomBytes } from 'node:crypto';
import test from 'node:test';
import { NYX_CONTENT } from './fixtures/nyx.mjs';

const base = process.env.ATLAS_TEST_URL;
test('whole Nyx paragraph researches and saved content gets persistent licensed images', {skip:!base}, async (t) => {
  const origin = new URL(base).origin;
  const password = randomBytes(24).toString('base64url');
  const email = `atlas-images-${randomBytes(10).toString('hex')}@example.invalid`;
  let cookie = '';
  async function request(path, body, method = body === undefined ? 'GET' : 'POST') {
    const response = await fetch(origin+path,{method,headers:{origin,...(cookie ? {cookie} : {}),...(body !== undefined ? {'content-type':'application/json'} : {})},body:body === undefined ? undefined : JSON.stringify(body)});
    const raw = await response.text();
    assert.match(response.headers.get('content-type') ?? '', /application\/json/, `${method} ${path}: HTTP ${response.status}, ${raw.slice(0, 160)}`);
    const result = JSON.parse(raw);
    return {response,result};
  }
  const anonymous = await request('/api/entries/missing/illustrations',{});
  assert.equal(anonymous.response.status,401);
  const signup = await request('/api/auth/sign-up/email',{email,password,name:'Image check'});
  assert.equal(signup.response.status,200,signup.result.message);
  cookie = signup.response.headers.getSetCookie().map(v=>v.split(';')[0]).join('; ');
  t.after(async () => {
    const cleanup = await request('/api/auth/delete-user',{password});
    assert.equal(cleanup.response.status,200,'Remove diagnostic account and entries');
  });
  assert.ok(NYX_CONTENT.length > 400);
  const searched = await request('/api/research',{content:NYX_CONTENT});
  assert.equal(searched.response.status,200);
  assert.equal(searched.result.error,undefined,searched.result.error);
  assert.equal(searched.result.title,'Nyx');
  assert.ok(searched.result.facts.length > 0);
  assert.ok(searched.result.images.length > 0,'Whole paragraph search includes Nyx images');
  const created = await request('/api/entries',{content:NYX_CONTENT});
  assert.equal(created.response.status,201);
  const {id} = created.result.entry;
  assert.equal(created.result.entry.title,'Nyx');
  const marked = await request(`/api/entries/${id}`,{annotations:[{start:0,end:18,color:'yellow'}]},'PATCH');
  assert.equal(marked.response.status,200);
  const illustrated = await request(`/api/entries/${id}/illustrations`,{});
  assert.equal(illustrated.response.status,200);
  assert.equal(illustrated.result.status,'ready');
  assert.equal(illustrated.result.entry.content,NYX_CONTENT,'Images never replace or add entry text');
  assert.deepEqual(illustrated.result.entry.annotations,marked.result.entry.annotations,'Markings survive image enrichment');
  assert.ok(illustrated.result.entry.images.length > 0);
  for (const image of illustrated.result.entry.images) {
    assert.ok(image.license);
    assert.equal(new URL(image.sourceUrl).hostname,'commons.wikimedia.org');
    assert.equal(new URL(image.url).protocol,'https:');
  }
  const thumbnail = await fetch(illustrated.result.entry.images[0].thumbnail);
  assert.equal(thumbnail.status,200,'First reference image is actually loadable');
  assert.match(thumbnail.headers.get('content-type'),/^image\//);
  await thumbnail.arrayBuffer();
  const saved = await request('/api/entries');
  const own = saved.result.entries.find(e=>e.id===id);
  assert.equal(own.content,NYX_CONTENT);
  assert.deepEqual(own.images,illustrated.result.entry.images,'Images persist when the dictionary reloads');
  const unchanged = await request(`/api/entries/${id}/illustrations`,{});
  assert.deepEqual(unchanged.result.entry.images,own.images,'Reopening never duplicates images');
});
