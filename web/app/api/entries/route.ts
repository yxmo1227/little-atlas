import { env } from 'cloudflare:workers';
import { getAtlasUser } from '@/lib/auth';
import { organizeEntry, parseEntry, validateEntryInput, InputError } from '@/lib/entry-data';
import { json, readBody, validMutation } from '@/lib/http';

export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  const user = await getAtlasUser(request);
  if (!user) return json({ error: 'Sign in to open your notebook.' }, 401);
  const rows = await env.DB!.prepare('SELECT * FROM atlas_entries WHERE user_id = ? ORDER BY updated_at DESC').bind(user.id).all();
  return json({ entries: rows.results.map(parseEntry) });
}

export async function POST(request: Request) {
  if (!validMutation(request)) return json({ error: 'This request is not allowed.' }, 403);
  const user = await getAtlasUser(request);
  if (!user) return json({ error: 'Sign in to save your content.' }, 401);
  try {
    const input = validateEntryInput(await readBody(request));
    const metadata = organizeEntry(input);
    const id = crypto.randomUUID(), now = new Date().toISOString();
    await env.DB!.prepare('INSERT INTO atlas_entries (id,user_id,title,content,blocks,revision,category,subcategory,sources,images,annotations,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)')
      .bind(id,user.id,metadata.title,input.content,JSON.stringify(input.blocks),0,metadata.category,metadata.subcategory,JSON.stringify(input.sources),JSON.stringify(input.images),JSON.stringify(input.annotations),now,now).run();
    return json({ entry: { ...input,...metadata,id,revision:0,createdAt:now,updatedAt:now } },201);
  } catch (error) {
    if (error instanceof InputError || error instanceof SyntaxError) return json({ error: error.message },400);
    console.error('entry creation failed', error instanceof Error ? error.message : 'unknown');
    return json({ error: 'Could not save your content. Please try again.' },500);
  }
}
