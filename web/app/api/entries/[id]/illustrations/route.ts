import { env } from 'cloudflare:workers';
import { getAtlasUser } from '@/lib/auth';
import { parseEntry, validateEntryInput, InputError } from '@/lib/entry-data';
import { researchImages } from '@/lib/knowledge';
import { json, readBody, validMutation } from '@/lib/http';
import { allowResearch } from '@/lib/research-limit';

export const dynamic = 'force-dynamic';
type Context = { params: Promise<{ id: string }> };

/** Enrich an existing private entry without changing its text or annotations. */
export async function POST(request: Request, context: Context) {
  if (!validMutation(request)) return json({error:'This request is not allowed.'},403);
  const user = await getAtlasUser(request);
  if (!user) return json({error:'Sign in to find images for your entry.'},401);
  const { id } = await context.params;
  const load = () => env.DB!.prepare('SELECT * FROM atlas_entries WHERE id = ? AND user_id = ?').bind(id,user.id).first();
  const row = await load();
  if (!row) return json({error:'Entry not found.'},404);
  const previous = parseEntry(row);
  try {
    await readBody(request);
    if (previous.images.length) return json({entry:previous,status:'ready'});
    if (!await allowResearch(user.id)) return json({error:'Take a moment before finding more images.'},429);
    const images = (await researchImages(previous.content)).slice(0,3);
    if (images.length) {
      const safe = validateEntryInput({images}, previous).images;
      // An edit, manual image selection, or deletion during lookup wins over this request.
      await env.DB!.prepare("UPDATE atlas_entries SET images=? WHERE id=? AND user_id=? AND content=? AND images='[]'")
        .bind(JSON.stringify(safe),id,user.id,previous.content).run();
    }
    const currentRow = await load();
    if (!currentRow) return json({error:'Entry not found.'},404);
    const entry = parseEntry(currentRow);
    return json({entry,status:entry.content === previous.content && entry.images.length ? 'ready' : 'unavailable'});
  } catch (error) {
    if (error instanceof InputError) return json({error:error.message},400);
    console.error('reference image lookup failed',error instanceof Error ? error.message : 'unknown');
    const currentRow = await load();
    if (!currentRow) return json({error:'Entry not found.'},404);
    return json({entry:parseEntry(currentRow),status:'unavailable'});
  }
}
