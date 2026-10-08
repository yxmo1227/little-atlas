import { getAtlasUser } from '@/lib/auth';
import { json } from '@/lib/http';

export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  return json({ user: await getAtlasUser(request) });
}
