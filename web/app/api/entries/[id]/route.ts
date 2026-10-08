import { env } from 'cloudflare:workers';
import { getAtlasUser } from '@/lib/auth';
import { organizeEntry, parseEntry, validateEntryInput, InputError } from '@/lib/entry-data';
import { json, readBody, validMutation } from '@/lib/http';

export const dynamic = 'force-dynamic';
type Context = { params: Promise<{ id: string }> };

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
    const changes: string[] = [], values: string[] = [];
    if (Object.hasOwn(fields,'content')) { changes.push('content=?'); values.push(input.content); }
    if (Object.hasOwn(fields,'sources')) { changes.push('sources=?'); values.push(JSON.stringify(input.sources)); }
    if (Object.hasOwn(fields,'images')) { changes.push('images=?'); values.push(JSON.stringify(input.images)); }
    if (Object.hasOwn(fields,'annotations') || input.content !== previous.content) { changes.push('annotations=?'); values.push(JSON.stringify(input.annotations)); }
    if (Object.hasOwn(fields,'content') || Object.hasOwn(fields,'sources')) {
      const metadata = organizeEntry(input);
      changes.push('title=?','category=?','subcategory=?'); values.push(metadata.title,metadata.category,metadata.subcategory);
    }
    if (!changes.length) return json({entry:previous});
    changes.push('updated_at=?'); values.push(new Date().toISOString());
    // Partial writes preserve concurrently fetched pictures; reject conflicting text/mark edits.
    const updated = await env.DB!.prepare(`UPDATE atlas_entries SET ${changes.join(',')} WHERE id=? AND user_id=? AND updated_at=?`)
      .bind(...values,id,user.id,previous.updatedAt).run();
    if (!updated.meta.changes) return json({error:'This entry changed while saving. Reopen it and try again.'},409);
    const current = await env.DB!.prepare('SELECT * FROM atlas_entries WHERE id=? AND user_id=?').bind(id,user.id).first();
    if (!current) return json({error:'Entry not found.'},404);
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
