export function json(value: unknown, status = 200) {
  return Response.json(value, { status, headers: { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' } });
}

export function validMutation(request: Request): boolean {
  const origin = request.headers.get('origin');
  return (!origin || origin === new URL(request.url).origin) &&
    (request.headers.get('content-type') ?? '').startsWith('application/json');
}

export async function readBody(request: Request): Promise<unknown> {
  const declared = Number(request.headers.get('content-length'));
  if (declared > 150_000) throw new InputError('This entry is too large.');
  const text = await request.text();
  if (text.length > 150_000) throw new InputError('This entry is too large.');
  try { return JSON.parse(text); } catch { throw new InputError('The entry could not be read.'); }
}
import { InputError } from './entry-data';

