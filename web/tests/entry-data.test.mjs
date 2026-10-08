import test from 'node:test';
import assert from 'node:assert/strict';
// Run with the project's tsx loader, or build this module with esbuild before Node testing.
import { validateEntryInput, organizeEntry } from '../lib/entry-data.ts';

test('content alone generates title and chapter without title or category fields', () => {
  const data = validateEntryInput({content:'Erebus is a primordial deity in Greek mythology.\nHe personifies darkness.', title:'ignored',category:'ignored'});
  const meta = organizeEntry(data);
  assert.equal(meta.title,'Erebus');
  assert.equal(meta.category,'Myths & Beliefs');
  assert.deepEqual(data.annotations,[]);
});

test('research context organizes exact selected wording', () => {
  const data = validateEntryInput({content:'He personifies darkness.',sources:[{url:'https://en.wikipedia.org/wiki/Erebus',title:'Erebus'}]});
  assert.equal(data.content,'He personifies darkness.');
  assert.equal(organizeEntry(data).title,'Erebus');
  assert.equal(organizeEntry(data).category,'Myths & Beliefs');
  assert.equal(organizeEntry(data).subcategory,'Greek Mythology');
});

test('only valid text ranges can be persisted, and edits clear obsolete marks', () => {
  const previous = validateEntryInput({content:'A useful discovery.',annotations:[{start:2,end:8,color:'yellow'}]});
  assert.throws(()=>validateEntryInput({content:'short',annotations:[{start:0,end:90,color:'red'}]}));
  assert.deepEqual(validateEntryInput({content:'Different content.'},previous).annotations,[]);
});

test('sources and image links cannot inject script or non-HTTPS content', () => {
  assert.throws(()=>validateEntryInput({content:'Some words.',sources:[{url:'javascript:alert(1)',title:'bad'}]}));
  assert.throws(()=>validateEntryInput({content:'Some words.',images:[{url:'https://example.org/a',thumbnail:'data:text/html,<script>',sourceUrl:'https://example.org',caption:'x'}]}));
});

test('empty and unbounded entries are rejected', () => {
  assert.throws(()=>validateEntryInput({content:' '}));
  assert.throws(()=>validateEntryInput({content:'x'.repeat(30_001)}));
});
