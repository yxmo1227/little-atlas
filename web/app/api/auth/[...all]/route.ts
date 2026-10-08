import { getAtlasAuth } from "@/lib/auth";

export const dynamic = "force-dynamic";

async function handle(request: Request) {
  try {
    return await getAtlasAuth().handler(request);
  } catch {
    return Response.json(
      { error: { message: "Email accounts are temporarily unavailable. Please try again later." } },
      { status: 503 },
    );
  }
}

export const GET = handle;
export const POST = handle;
