import { classifyContent, type ResearchImage } from './knowledge';
import { blocksFromContent, contentFromBlocks, MAX_NOTEBOOK_CONTENT, NotebookInputError, validateNotebookBlocks, type NotebookBlock } from './notebook';

export type Source = { url: string; title: string };
export type Annotation = { start: number; end: number; color: 'yellow' | 'red' };
export type EntryInput = {
  content: string; blocks: NotebookBlock[]; sources: Source[]; images: ResearchImage[]; annotations: Annotation[];
  title?: string; category?: string; subcategory?: string;
};
export type Entry = EntryInput & { id: string; title: string; category: string; subcategory: string; revision: number; createdAt: string; updatedAt: string };

export class InputError extends Error {}

function httpsLink(value: unknown): string {
  if (typeof value !== 'string' || value.length > 2048) throw new InputError('A source link is invalid.');
  try {
    const url = new URL(value);
    if (url.protocol !== 'https:' || url.username || url.password) throw new Error();
    return url.href;
  } catch { throw new InputError('Use a complete HTTPS source link.'); }
}

function shortText(value: unknown, max: number): string {
  return typeof value === 'string' ? value.replace(/[\u0000-\u0008\u000b-\u001f]/g, '').slice(0, max) : '';
}

function metadataText(value: unknown, name: string, max: number): string {
  const optional = name === 'subcategory';
  if (typeof value !== 'string' || (!optional && !value.trim()) || value.length > max || /[\u0000-\u001f]/.test(value)) {
    throw new InputError(`Use ${optional ? 'a' : 'a nonempty'} ${name} of up to ${max} characters.`);
  }
  return value.trim();
}

/** Keep markings on unchanged words when text is inserted, deleted, or replaced. */
export function remapAnnotations(previous: string, content: string, annotations: Annotation[]): Annotation[] {
  if (previous === content) return annotations.map((mark) => ({ ...mark }));
  let prefix = 0;
  while (prefix < previous.length && prefix < content.length && previous[prefix] === content[prefix]) prefix++;
  let suffix = 0;
  while (suffix < previous.length - prefix && suffix < content.length - prefix &&
    previous[previous.length - suffix - 1] === content[content.length - suffix - 1]) suffix++;
  const modifiedEnd = previous.length - suffix;
  const delta = content.length - previous.length;
  return annotations.flatMap((mark) => {
    if (mark.end <= prefix) return [{ ...mark }];
    if (mark.start >= modifiedEnd) return [{ ...mark, start: mark.start + delta, end: mark.end + delta }];
    return [];
  });
}

export function validateEntryInput(raw: unknown, previous?: EntryInput): EntryInput {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new InputError('Content is required.');
  const input = raw as Record<string, unknown>;
  let content: string, blocks: NotebookBlock[];
  try {
    if (Object.hasOwn(input, 'blocks')) {
      blocks = validateNotebookBlocks(input.blocks);
      content = contentFromBlocks(blocks);
      if (Object.hasOwn(input, 'content') && input.content !== content) {
        throw new InputError('The note text and its blocks must match.');
      }
    } else {
      const original = Object.hasOwn(input, 'content') ? input.content : previous?.content;
      if (typeof original !== 'string' || !original.trim()) throw new InputError('Write some content first.');
      if (original.length > MAX_NOTEBOOK_CONTENT) throw new InputError('Keep one note under 200,000 characters.');
      content = original;
      blocks = Object.hasOwn(input, 'content') ? blocksFromContent(content) : previous?.blocks ?? blocksFromContent(content);
    }
  } catch (error) {
    if (error instanceof NotebookInputError) throw new InputError(error.message);
    throw error;
  }
  const metadata: Pick<EntryInput, 'title' | 'category' | 'subcategory'> = {};
  for (const [key, max] of [['title',120], ['category',80], ['subcategory',120]] as const) {
    if (Object.hasOwn(input, key)) metadata[key] = metadataText(input[key], key, max);
    else if (previous?.[key] !== undefined) metadata[key] = previous[key];
  }
  const rawSources = Object.hasOwn(input, 'sources') ? input.sources : previous?.sources ?? [];
  if (!Array.isArray(rawSources) || rawSources.length > 30) throw new InputError('Too many sources.');
  const sources = rawSources.map((source) => {
    if (!source || typeof source !== 'object') throw new InputError('A source is invalid.');
    return { url: httpsLink(source.url), title: shortText(source.title, 160) };
  });
  const rawImages = Object.hasOwn(input, 'images') ? input.images : previous?.images ?? [];
  if (!Array.isArray(rawImages) || rawImages.length > 12) throw new InputError('Choose up to 12 images.');
  const images = rawImages.map((image) => {
    if (!image || typeof image !== 'object') throw new InputError('An image is invalid.');
    return { url: httpsLink(image.url), thumbnail: httpsLink(image.thumbnail || image.url),
      sourceUrl: httpsLink(image.sourceUrl), caption: shortText(image.caption, 300),
      license: shortText(image.license, 160), attribution: shortText(image.attribution, 500) };
  });
  const rawAnnotations = Object.hasOwn(input, 'annotations') ? input.annotations :
    previous ? remapAnnotations(previous.content, content, previous.annotations) : [];
  if (!Array.isArray(rawAnnotations) || rawAnnotations.length > 500) throw new InputError('Too many markings in this entry.');
  const annotations = rawAnnotations.map((mark) => {
    if (!mark || typeof mark !== 'object' || !Number.isInteger(mark.start) || !Number.isInteger(mark.end) ||
        mark.start < 0 || mark.end <= mark.start || mark.end > content.length || !['yellow','red'].includes(mark.color)) {
      throw new InputError('A marking does not match the entry text.');
    }
    return { start: mark.start, end: mark.end, color: mark.color } as Annotation;
  });
  return { content, blocks, sources, images, annotations, ...metadata };
}

export function organizeEntry(input: EntryInput) {
  const sourceTitle = input.sources.find((source) => source.title)?.title;
  const organized = classifyContent(sourceTitle ? `${sourceTitle}\n${input.content}` : input.content);
  return {
    title: input.title ?? (sourceTitle || organized.title).slice(0, 120),
    category: input.category ?? organized.category,
    subcategory: input.subcategory ?? organized.subcategory,
  };
}

export function parseEntry(row: Record<string, unknown>): Entry {
  const content = String(row.content);
  const savedBlocks = JSON.parse(String(row.blocks ?? '[]'));
  return {
    id: String(row.id), title: String(row.title), content,
    blocks: Array.isArray(savedBlocks) && savedBlocks.length ? savedBlocks : blocksFromContent(content),
    revision: Number(row.revision ?? 0),
    category: String(row.category), subcategory: String(row.subcategory),
    sources: JSON.parse(String(row.sources)), images: JSON.parse(String(row.images)),
    annotations: JSON.parse(String(row.annotations)), createdAt: String(row.created_at), updatedAt: String(row.updated_at),
  };
}
