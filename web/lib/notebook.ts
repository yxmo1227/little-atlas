export type NotebookBlock = { id: string; type: 'paragraph' | 'heading1' | 'heading2'; text: string };

export const MAX_NOTEBOOK_CONTENT = 200_000;
export const MAX_NOTEBOOK_BLOCKS = 1_000;

export class NotebookInputError extends Error {}

/** The separators are part of the plain-text projection used by search and markings. */
export function contentFromBlocks(blocks: NotebookBlock[]): string {
  return blocks.map((block) => block.text).join('\n\n');
}

/** A section heading is navigation, not necessarily the subject of the article. */
export function notebookResearchQuery(blocks: NotebookBlock[], content: string, sources: { url: string }[]): string {
  for (const source of sources) {
    try {
      const url = new URL(source.url);
      if (url.protocol === 'https:' && url.hostname === 'en.wikipedia.org' && url.pathname.startsWith('/wiki/')) {
        const title = decodeURIComponent(url.pathname.slice(6)).replace(/_/g, ' ').trim();
        if (title && !title.includes(':')) return title;
      }
    } catch { /* Fall back to the saved body for other or malformed source links. */ }
  }
  return blocks.filter((block) => block.type === 'paragraph' && block.text.trim()).map((block) => block.text).join('\n\n') || content;
}

/** Legacy notes retain every character, with deterministic IDs until their first edit. */
export function blocksFromContent(content: string): NotebookBlock[] {
  const paragraphs = content.split('\n\n');
  if (paragraphs.length > MAX_NOTEBOOK_BLOCKS) {
    paragraphs.splice(MAX_NOTEBOOK_BLOCKS - 1, paragraphs.length, paragraphs.slice(MAX_NOTEBOOK_BLOCKS - 1).join('\n\n'));
  }
  return paragraphs.map((text, index) => ({ id: `paragraph-${index + 1}`, type: 'paragraph', text }));
}

export function validateNotebookBlocks(value: unknown): NotebookBlock[] {
  if (!Array.isArray(value) || !value.length || value.length > MAX_NOTEBOOK_BLOCKS) {
    throw new NotebookInputError('Use between 1 and 1,000 blocks in a note.');
  }
  const ids = new Set<string>();
  const blocks = value.map((item) => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) throw new NotebookInputError('A note block is invalid.');
    const block = item as Record<string, unknown>;
    if (typeof block.id !== 'string' || !block.id.trim() || block.id.length > 100 || /[\u0000-\u001f]/.test(block.id) || ids.has(block.id)) {
      throw new NotebookInputError('Each note block needs a unique ID.');
    }
    if (block.type !== 'paragraph' && block.type !== 'heading1' && block.type !== 'heading2') {
      throw new NotebookInputError('Choose a paragraph or a heading for each block.');
    }
    if (typeof block.text !== 'string' || block.text.length > MAX_NOTEBOOK_CONTENT) throw new NotebookInputError('A note block is too large.');
    ids.add(block.id);
    return { id: block.id, type: block.type, text: block.text } as NotebookBlock;
  });
  const content = contentFromBlocks(blocks);
  if (!content.trim()) throw new NotebookInputError('Write some content first.');
  if (content.length > MAX_NOTEBOOK_CONTENT) throw new NotebookInputError('Keep one note under 200,000 characters.');
  return blocks;
}
