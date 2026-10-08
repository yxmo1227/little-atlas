import { env } from 'cloudflare:workers';

/** Share the same per-account allowance between topic searches and automatic images. */
export async function allowResearch(userId: string): Promise<boolean> {
  const minute = Math.floor(Date.now() / 60_000);
  const rate = await env.DB!.prepare('INSERT INTO atlas_search_rate (user_id,window_start,count) VALUES (?,?,1) ON CONFLICT(user_id) DO UPDATE SET count=CASE WHEN window_start<>excluded.window_start THEN 1 ELSE count+1 END,window_start=excluded.window_start RETURNING count')
    .bind(userId, minute).first<{ count: number }>();
  return !rate || rate.count <= 30;
}
