import test from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';
// Bundle the TypeScript's extensionless imports without changing production module resolution.
const compiled = await build({ entryPoints: [fileURLToPath(new URL('../lib/entry-data.ts', import.meta.url))], bundle:true, platform:'node', format:'esm', write:false });
const { validateEntryInput, organizeEntry, parseEntry, InputError, remapAnnotations } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString('base64')}`);

test('content alone generates title and chapter without title or category fields', () => {
  const data = validateEntryInput({content:'Erebus is a primordial deity in Greek mythology.\nHe personifies darkness.'});
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
  assert.equal(validateEntryInput({content:'x'.repeat(200_000)}).content.length,200_000);
  assert.throws(()=>validateEntryInput({content:'x'.repeat(200_001)}));
});

test('explicit notebook metadata overrides automatic organization and survives text edits', () => {
  const previous = validateEntryInput({ content:'Nyx is the goddess of night.', title:'My Greek notes', category:'Mythology reading', subcategory:'Family trees' });
  assert.deepEqual(organizeEntry(previous), {title:'My Greek notes',category:'Mythology reading',subcategory:'Family trees'});
  const updated = validateEntryInput({content:'Octopuses have three hearts.'}, previous);
  assert.equal(updated.title,'My Greek notes');
  assert.equal(updated.category,'Mythology reading');
  assert.equal(updated.subcategory,'Family trees');
  assert.equal(validateEntryInput({title:'Updated reading'},previous).title,'Updated reading');
  for (const field of ['title','category','subcategory']) {
    if (field !== 'subcategory') assert.throws(()=>validateEntryInput({[field]:' '},previous),InputError);
    assert.throws(()=>validateEntryInput({[field]:'x'.repeat(121)},previous),InputError);
  }
});

test('an optional subcategory can be cleared and remains empty on later content edits', () => {
  const previous = validateEntryInput({content:'Nyx is the goddess of night.',subcategory:'Greek Mythology'});
  for (const subcategory of ['', '   ']) {
    const cleared = validateEntryInput({subcategory},previous);
    assert.equal(cleared.subcategory,'');
    assert.equal(organizeEntry(cleared).subcategory,'');
    assert.equal(validateEntryInput({content:'Nyx has many children.'},cleared).subcategory,'');
  }
  assert.throws(()=>validateEntryInput({subcategory:null},previous),InputError);
});

test('blocks persist heading structure and plain text consistently', () => {
  const blocks = [
    {id:'intro',type:'heading1',text:'Introduction'},
    {id:'body',type:'paragraph',text:'A discovery.\nA follow-up.'},
    {id:'detail',type:'heading2',text:'More detail'},
  ];
  const data = validateEntryInput({blocks});
  assert.deepEqual(data.blocks,blocks);
  assert.equal(data.content,'Introduction\n\nA discovery.\nA follow-up.\n\nMore detail');
  assert.deepEqual(validateEntryInput({blocks,content:data.content}).blocks,blocks);
  assert.throws(()=>validateEntryInput({blocks,content:'different'}),InputError);
  assert.throws(()=>validateEntryInput({blocks:[blocks[0],{...blocks[1],id:'intro'}]}),InputError);
  assert.throws(()=>validateEntryInput({blocks:[{id:'unsupported',type:'script',text:'No'}]}),InputError);
  assert.throws(()=>validateEntryInput({blocks:Array.from({length:1001},(_,i)=>({id:`b-${i}`,type:'paragraph',text:'x'}))}),InputError);
});

test('old text rows open as editable blocks without changing saved text or timestamps', () => {
  const text = '  First paragraph.\r\n\r\nSecond paragraph.\n\n\nTrailing whitespace.  ';
  const row = {id:'old-entry',title:'Original name',content:text,category:'General',subcategory:'My notes',sources:'[]',images:'[]',annotations:'[]',created_at:'2026-10-07',updated_at:'2026-10-08'};
  const entry = parseEntry(row);
  assert.equal(entry.content,text);
  assert.equal(entry.revision,0);
  assert.equal(entry.updatedAt,row.updated_at);
  assert.deepEqual(entry.blocks,parseEntry({...row,blocks:'[]',revision:0}).blocks);
  assert.equal(entry.blocks.map((block)=>block.text).join('\n\n'),text);
  const saved = parseEntry({...row,blocks:JSON.stringify([{id:'custom',type:'heading1',text:'Custom heading'}]),revision:7});
  assert.equal(saved.blocks[0].type,'heading1');
  assert.equal(saved.revision,7);
});

test('partial markings and metadata updates preserve saved images and headings', () => {
  const images = [{url:'https://example.org/image.png',sourceUrl:'https://example.org/reference',caption:'A reference',license:'CC0',attribution:'Example'}];
  const previous = validateEntryInput({blocks:[{id:'section',type:'heading1',text:'A heading'},{id:'text',type:'paragraph',text:'A useful discovery.'}],images});
  const updated = validateEntryInput({annotations:[{start:11,end:17,color:'yellow'}]},previous);
  assert.deepEqual(updated.images,previous.images);
  assert.deepEqual(updated.blocks,previous.blocks);
  const compatibility = validateEntryInput({content:'Different words.'},previous);
  assert.equal(compatibility.blocks[0].type,'paragraph');
  assert.deepEqual(compatibility.annotations,[]);
  assert.deepEqual(compatibility.images,previous.images);
});

test('appending paragraphs retains highlights on the previous text', () => {
  const previous = validateEntryInput({content:'Alpha beta gamma.',annotations:[{start:0,end:5,color:'yellow'},{start:11,end:16,color:'red'}]});
  const updated = validateEntryInput({content:`${previous.content}\n\nA new paragraph.`},previous);
  assert.deepEqual(updated.annotations,previous.annotations);
});

test('prepending text shifts highlights to the same original words', () => {
  const previous = validateEntryInput({content:'Alpha beta gamma.',annotations:[{start:6,end:10,color:'yellow'}]});
  const updated = validateEntryInput({content:`Intro.\n\n${previous.content}`},previous);
  assert.deepEqual(updated.annotations,[{start:14,end:18,color:'yellow'}]);
  assert.equal(updated.content.slice(updated.annotations[0].start,updated.annotations[0].end),'beta');
});

test('a middle edit removes only overlapping marks and shifts later unchanged words', () => {
  const previous = 'Alpha beta gamma.';
  const marks = [{start:0,end:5,color:'yellow'},{start:6,end:10,color:'yellow'},{start:11,end:16,color:'red'}];
  const updated = remapAnnotations(previous,'Alpha b gamma.',marks);
  assert.deepEqual(updated,[{start:0,end:5,color:'yellow'},{start:8,end:13,color:'red'}]);
  assert.deepEqual(remapAnnotations('Alpha beta gamma.','Alpha beta extra gamma.',marks),[
    {start:0,end:5,color:'yellow'},{start:6,end:10,color:'yellow'},{start:17,end:22,color:'red'},
  ]);
  assert.deepEqual(remapAnnotations(previous,previous,marks),marks);
  assert.deepEqual(marks[2],{start:11,end:16,color:'red'});
});

test('an explicit marking list remains authoritative after an edit', () => {
  const previous = validateEntryInput({content:'Alpha beta gamma.',annotations:[{start:0,end:5,color:'yellow'}]});
  assert.deepEqual(validateEntryInput({content:`${previous.content}\n\nMore.`,annotations:[]},previous).annotations,[]);
});
