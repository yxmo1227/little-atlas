import { classifyContent, type ResearchImage } from './knowledge';

export type Source = { url: string; title: string };
export type Annotation = { start: number; end: number; color: 'yellow' | 'red' };
export type EntryInput = { content: string; sources: Source[]; images: ResearchImage[]; annotations: Annotation[] };
export type Entry = EntryInput & { id: string; title: string; category: string; subcategory: string; createdAt: string; updatedAt: string };

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

export function validateEntryInput(raw: unknown, previous?: EntryInput): EntryInput {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new InputError('Content is required.');
  const input = raw as Record<string, unknown>;
  const original = input.content ?? previous?.content;
  if (typeof original !== 'string' || !original.trim()) throw new InputError('Write some content first.');
  if (original.length > 30_000) throw new InputError('Keep one entry under 30,000 characters.');
  const content = original.replace(/\r\n?/g, '\n').trim();
  const rawSources = input.sources ?? previous?.sources ?? [];
  if (!Array.isArray(rawSources) || rawSources.length > 30) throw new InputError('Too many sources.');
  const sources = rawSources.map((source) => {
    if (!source || typeof source !== 'object') throw new InputError('A source is invalid.');
    return { url: httpsLink(source.url), title: shortText(source.title, 160) };
  });
  const rawImages = input.images ?? previous?.images ?? [];
  if (!Array.isArray(rawImages) || rawImages.length > 12) throw new InputError('Choose up to 12 images.');
  const images = rawImages.map((image) => {
    if (!image || typeof image !== 'object') throw new InputError('An image is invalid.');
    return { url: httpsLink(image.url), thumbnail: httpsLink(image.thumbnail || image.url),
      sourceUrl: httpsLink(image.sourceUrl), caption: shortText(image.caption, 300),
      license: shortText(image.license, 160), attribution: shortText(image.attribution, 500) };
  });
  // Edits change offsets. Preserve markings only when the underlying words stay the same.
  const rawAnnotations = input.annotations ?? (content === previous?.content ? previous.annotations : []) ?? [];
  if (!Array.isArray(rawAnnotations) || rawAnnotations.length > 500) throw new InputError('Too many markings in this entry.');
  const annotations = rawAnnotations.map((mark) => {
    if (!mark || typeof mark !== 'object' || !Number.isInteger(mark.start) || !Number.isInteger(mark.end) ||
        mark.start < 0 || mark.end <= mark.start || mark.end > content.length || !['yellow','red'].includes(mark.color)) {
      throw new InputError('A marking does not match the entry text.');
    }
    return { start: mark.start, end: mark.end, color: mark.color } as Annotation;
  });
  return { content, sources, images, annotations };
}

export function organizeEntry(input: EntryInput) {
  const sourceTitle = input.sources.find((source) => source.title)?.title;
  const organized = classifyContent(sourceTitle ? `${sourceTitle}\n${input.content}` : input.content);
  return { title: sourceTitle || organized.title, category: organized.category, subcategory: organized.subcategory };
}

export function parseEntry(row: Record<string, unknown>): Entry {
  return {
    id: String(row.id), title: String(row.title), content: String(row.content),
    category: String(row.category), subcategory: String(row.subcategory),
    sources: JSON.parse(String(row.sources)), images: JSON.parse(String(row.images)),
    annotations: JSON.parse(String(row.annotations)), createdAt: String(row.created_at), updatedAt: String(row.updated_at),
  };
}
