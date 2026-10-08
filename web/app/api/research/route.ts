import { getAtlasUser } from '@/lib/auth';
import { researchTopic } from '@/lib/knowledge';
import { json, readBody, validMutation } from '@/lib/http';
import { InputError } from '@/lib/entry-data';
import { allowResearch } from '@/lib/research-limit';

export const dynamic = 'force-dynamic';

async function research(request: Request, query: unknown) {
  const user = await getAtlasUser(request);
  if (!user) return json({error:'Sign in to research and save your discoveries.'},401);
  if (typeof query !== 'string' || !query.trim() || query.length > 30_000) return json({error:'Enter a topic or content of up to 30,000 characters.'},400);
  if (!await allowResearch(user.id)) return json({error:'Take a moment before searching again.'},429);
  return json(await researchTopic(query.trim()));
}

export async function GET(request: Request) {
  return research(request, new URL(request.url).searchParams.get('q'));
}

export async function POST(request: Request) {
  if (!validMutation(request)) return json({error:'This request is not allowed.'},403);
  try {
    const body = await readBody(request);
    const query = body && typeof body === 'object' && !Array.isArray(body) ? (body as Record<string,unknown>).content : undefined;
    return await research(request, query);
  } catch (error) {
    if (error instanceof InputError) return json({error:error.message},400);
    throw error;
  }
}
