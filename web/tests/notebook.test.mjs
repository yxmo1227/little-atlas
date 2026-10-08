import test from 'node:test';
import assert from 'node:assert/strict';
import { blocksFromContent, contentFromBlocks, validateNotebookBlocks, notebookResearchQuery } from '../lib/notebook.ts';

test('notebook pictures use the article subject rather than a generic section heading', () => {
  const blocks = [{id:'heading',type:'heading1',text:'The night goddess'},{id:'body',type:'paragraph',text:'Nyx is the Greek goddess of the night.'}];
  assert.equal(notebookResearchQuery(blocks,contentFromBlocks(blocks),[]),'Nyx is the Greek goddess of the night.');
  assert.equal(notebookResearchQuery(blocks,contentFromBlocks(blocks),[{url:'https://en.wikipedia.org/wiki/Nyx'}]),'Nyx');
  assert.equal(notebookResearchQuery(blocks,contentFromBlocks(blocks),[{url:'https://example.com/wiki/Other'}]),'Nyx is the Greek goddess of the night.');
  assert.equal(notebookResearchQuery([{id:'heading',type:'heading1',text:'Nyx'}],'Nyx',[]),'Nyx');
});

test('legacy paragraph projection is lossless and its IDs remain stable on every read', () => {
  for (const content of ['First\n\nSecond', '\n\n\n\nIndented  words\n', 'One\r\nTwo', 'x\n\n'.repeat(1100)]) {
    const blocks = blocksFromContent(content);
    assert.equal(contentFromBlocks(blocks),content);
    assert.deepEqual(blocks,blocksFromContent(content));
    assert.ok(blocks.length <= 1000);
  }
});

test('empty editable blocks stay in structure but a completely empty note is not saved', () => {
  const blocks = [{id:'heading',type:'heading1',text:''},{id:'body',type:'paragraph',text:'Content'},{id:'later',type:'paragraph',text:''}];
  assert.deepEqual(validateNotebookBlocks(blocks),blocks);
  assert.throws(()=>validateNotebookBlocks([{id:'empty',type:'paragraph',text:'  '}]),/Write some content/);
});

test('aggregate block limit includes paragraph separators', () => {
  assert.throws(()=>validateNotebookBlocks([{id:'first',type:'paragraph',text:'x'.repeat(199999)},{id:'last',type:'paragraph',text:'x'}]),/200,000/);
});
