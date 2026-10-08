import { getAtlasUser } from '@/lib/auth';
import { researchTopic } from '@/lib/knowledge';
import { json, readBody, validMutation } from '@/lib/http';
import { InputError } from '@/lib/entry-data';
import { allowResearch } from '@/lib/research-limit';

export const dynamic = 'force-dynamic';

async function research(request: Request, query: unknown, exactTitle: unknown = false) {
  const user = await getAtlasUser(request);
  if (!user) return json({error:'Sign in to research and save your discoveries.'},401);
  if (typeof query !== 'string' || !query.trim() || query.length > 30_000) return json({error:'Enter a topic or content of up to 30,000 characters.'},400);
  if (typeof exactTitle !== 'boolean' || (exactTitle && query.length > 200)) return json({error:'Choose a valid reference article title.'},400);
  if (!await allowResearch(user.id)) return json({error:'Take a moment before searching again.'},429);
  return json(await researchTopic(query.trim(), exactTitle));
}

export async function GET(request: Request) {
  return research(request, new URL(request.url).searchParams.get('q'));
}

export async function POST(request: Request) {
  if (!validMutation(request)) return json({error:'This request is not allowed.'},403);
  try {
    const body = await readBody(request);
    const input = body && typeof body === 'object' && !Array.isArray(body) ? body as Record<string,unknown> : {};
    return await research(request, input.content, input.exactTitle ?? false);
  } catch (error) {
    if (error instanceof InputError) return json({error:error.message},400);
    throw error;
  }
}
