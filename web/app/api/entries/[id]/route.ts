import { env } from 'cloudflare:workers';
import { getAtlasUser } from '@/lib/auth';
import { parseEntry, validateEntryInput, InputError, type Entry } from '@/lib/entry-data';
import { json, readBody, validMutation } from '@/lib/http';

export const dynamic = 'force-dynamic';
type Context = { params: Promise<{ id: string }> };

function conflict(entry: Entry) {
  return json({ error: 'This note changed on another device. Review the latest version before saving.', code: 'CONFLICT', entry }, 409);
}

export async function GET(request: Request, context: Context) {
  const user = await getAtlasUser(request);
  if (!user) return json({ error: 'Sign in to open your notebook.' }, 401);
  const { id } = await context.params;
  const row = await env.DB!.prepare('SELECT * FROM atlas_entries WHERE id = ? AND user_id = ?').bind(id,user.id).first();
  if (!row) return json({ error: 'Entry not found.' }, 404);
  return json({ entry: parseEntry(row) });
}

export async function PATCH(request: Request, context: Context) {
  if (!validMutation(request)) return json({ error: 'This request is not allowed.' },403);
  const user = await getAtlasUser(request);
  if (!user) return json({ error: 'Sign in to save changes.' },401);
  const { id } = await context.params;
  const row = await env.DB!.prepare('SELECT * FROM atlas_entries WHERE id = ? AND user_id = ?').bind(id,user.id).first();
  if (!row) return json({ error: 'Entry not found.' },404);
  try {
    const previous = parseEntry(row);
    const body = await readBody(request);
    const input = validateEntryInput(body,previous);
    const fields = body as Record<string,unknown>;
    if (Object.hasOwn(fields, 'baseRevision')) {
      if (!Number.isSafeInteger(fields.baseRevision) || Number(fields.baseRevision) < 0) throw new InputError('The note revision is invalid.');
      if (fields.baseRevision !== previous.revision) return conflict(previous);
    }
    const changes: string[] = [], values: (string | number)[] = [];
    if (Object.hasOwn(fields,'content') || Object.hasOwn(fields,'blocks')) {
      if (input.content !== previous.content) { changes.push('content=?'); values.push(input.content); }
      if (JSON.stringify(input.blocks) !== JSON.stringify(previous.blocks)) { changes.push('blocks=?'); values.push(JSON.stringify(input.blocks)); }
    }
    for (const key of ['sources','images','annotations'] as const) {
      if ((Object.hasOwn(fields,key) || (key === 'annotations' && input.content !== previous.content)) && JSON.stringify(input[key]) !== JSON.stringify(previous[key])) {
        changes.push(`${key}=?`); values.push(JSON.stringify(input[key]));
      }
    }
    for (const key of ['title','category','subcategory'] as const) {
      if (Object.hasOwn(fields,key) && input[key] !== previous[key]) { changes.push(`${key}=?`); values.push(input[key]!); }
    }
    if (!changes.length) return json({entry:previous});
    changes.push('updated_at=?','revision=revision+1'); values.push(new Date().toISOString());
    // User edits share a revision; independent picture enrichment uses partial writes.
    const updated = await env.DB!.prepare(`UPDATE atlas_entries SET ${changes.join(',')} WHERE id=? AND user_id=? AND revision=?`)
      .bind(...values,id,user.id,previous.revision).run();
    const current = await env.DB!.prepare('SELECT * FROM atlas_entries WHERE id=? AND user_id=?').bind(id,user.id).first();
    if (!current) return json({error:'Entry not found.'},404);
    if (!updated.meta.changes) return conflict(parseEntry(current));
    return json({entry:parseEntry(current)});
  } catch (error) {
    if (error instanceof InputError || error instanceof SyntaxError) return json({ error:error.message },400);
    console.error('entry update failed', error instanceof Error ? error.message : 'unknown');
    return json({ error:'Could not save your changes. Please try again.' },500);
  }
}

export async function DELETE(request: Request, context: Context) {
  const origin = request.headers.get('origin');
  if (origin && origin !== new URL(request.url).origin) return json({error:'This request is not allowed.'},403);
  const user = await getAtlasUser(request);
  if (!user) return json({ error:'Sign in to delete an entry.' },401);
  const { id } = await context.params;
  const deleted = await env.DB!.prepare('DELETE FROM atlas_entries WHERE id = ? AND user_id = ?').bind(id,user.id).run();
  if (!deleted.meta.changes) return json({error:'Entry not found.'},404);
  return json({ok:true});
}
