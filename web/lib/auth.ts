import { env } from "cloudflare:workers";
import { betterAuth } from "better-auth/minimal";
import { drizzleAdapter } from "better-auth/adapters/drizzle";
import { getDb } from "@/db";
import {
  atlasAccount,
  atlasRateLimit,
  atlasSession,
  atlasUser,
  atlasVerification,
} from "@/db/schema";

export type AtlasUser = { id: string; email: string };

export function getAtlasAuth() {
  const secret = env.BETTER_AUTH_SECRET;
  const baseURL = env.BETTER_AUTH_URL;
  if (!secret || secret.length < 32 || !baseURL) {
    throw new Error("Email accounts are not configured yet.");
  }
  const origin = new URL(baseURL);
  const localHTTP = origin.protocol === "http:" && ["localhost", "127.0.0.1"].includes(origin.hostname);
  if (origin.protocol !== "https:" && !localHTTP) {
    throw new Error("Email accounts require a secure site URL.");
  }

  return betterAuth({
    appName: "Little Atlas",
    baseURL: origin.origin,
    basePath: "/api/auth",
    secret,
    trustedOrigins: [origin.origin],
    database: drizzleAdapter(getDb(), {
      provider: "sqlite",
      transaction: false,
      schema: {
        atlas_user: atlasUser,
        atlas_session: atlasSession,
        atlas_account: atlasAccount,
        atlas_verification: atlasVerification,
        atlas_rate_limit: atlasRateLimit,
      },
    }),
    emailAndPassword: {
      enabled: true,
      minPasswordLength: 10,
      maxPasswordLength: 128,
      requireEmailVerification: false,
      autoSignIn: true,
    },
    user: { modelName: "atlas_user", deleteUser: { enabled: true } },
    account: { modelName: "atlas_account", accountLinking: { enabled: false } },
    verification: { modelName: "atlas_verification" },
    session: {
      modelName: "atlas_session",
      expiresIn: 60 * 60 * 24 * 7,
      updateAge: 60 * 60 * 24,
      cookieCache: { enabled: false },
    },
    rateLimit: {
      enabled: true,
      storage: "database",
      modelName: "atlas_rate_limit",
      window: 60,
      max: 60,
      customRules: {
        "/sign-in/email": { window: 60, max: 5 },
        "/sign-up/email": { window: 60, max: 3 },
      },
    },
    advanced: {
      cookiePrefix: "little-atlas",
      useSecureCookies: origin.protocol === "https:",
      defaultCookieAttributes: { httpOnly: true, sameSite: "lax", path: "/" },
      ipAddress: { ipAddressHeaders: ["cf-connecting-ip"] },
    },
  });
}

export async function getAtlasUser(request: Request): Promise<AtlasUser | null> {
  const session = await getAtlasAuth().api.getSession({ headers: request.headers });
  if (!session?.user?.id || !session.user.email) return null;
  return { id: session.user.id, email: session.user.email };
}
