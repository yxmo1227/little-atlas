import { index, integer, sqliteTable, text, uniqueIndex } from "drizzle-orm/sqlite-core";

export const atlasUser = sqliteTable("atlas_user", {
  id: text("id").primaryKey(),
  name: text("name").notNull(),
  email: text("email").notNull().unique(),
  emailVerified: integer("email_verified", { mode: "boolean" }).notNull().default(false),
  image: text("image"),
  createdAt: integer("created_at", { mode: "timestamp_ms" }).notNull(),
  updatedAt: integer("updated_at", { mode: "timestamp_ms" }).notNull(),
});

export const atlasSession = sqliteTable("atlas_session", {
  id: text("id").primaryKey(),
  expiresAt: integer("expires_at", { mode: "timestamp_ms" }).notNull(),
  token: text("token").notNull().unique(),
  createdAt: integer("created_at", { mode: "timestamp_ms" }).notNull(),
  updatedAt: integer("updated_at", { mode: "timestamp_ms" }).notNull(),
  ipAddress: text("ip_address"),
  userAgent: text("user_agent"),
  userId: text("user_id").notNull().references(() => atlasUser.id, { onDelete: "cascade" }),
}, (table) => [index("atlas_session_user_idx").on(table.userId)]);

export const atlasAccount = sqliteTable("atlas_account", {
  id: text("id").primaryKey(),
  accountId: text("account_id").notNull(),
  providerId: text("provider_id").notNull(),
  userId: text("user_id").notNull().references(() => atlasUser.id, { onDelete: "cascade" }),
  accessToken: text("access_token"),
  refreshToken: text("refresh_token"),
  idToken: text("id_token"),
  accessTokenExpiresAt: integer("access_token_expires_at", { mode: "timestamp_ms" }),
  refreshTokenExpiresAt: integer("refresh_token_expires_at", { mode: "timestamp_ms" }),
  scope: text("scope"),
  password: text("password"),
  createdAt: integer("created_at", { mode: "timestamp_ms" }).notNull(),
  updatedAt: integer("updated_at", { mode: "timestamp_ms" }).notNull(),
}, (table) => [
  index("atlas_account_user_idx").on(table.userId),
  uniqueIndex("atlas_account_provider_idx").on(table.providerId, table.accountId),
]);

export const atlasVerification = sqliteTable("atlas_verification", {
  id: text("id").primaryKey(),
  identifier: text("identifier").notNull(),
  value: text("value").notNull(),
  expiresAt: integer("expires_at", { mode: "timestamp_ms" }).notNull(),
  createdAt: integer("created_at", { mode: "timestamp_ms" }).notNull(),
  updatedAt: integer("updated_at", { mode: "timestamp_ms" }).notNull(),
}, (table) => [index("atlas_verification_identifier_idx").on(table.identifier)]);

export const atlasRateLimit = sqliteTable("atlas_rate_limit", {
  id: text("id").primaryKey(),
  key: text("key").notNull().unique(),
  count: integer("count").notNull(),
  lastRequest: integer("last_request").notNull(),
});

export const atlasEntries = sqliteTable('atlas_entries', {
  id: text('id').primaryKey(),
  userId: text('user_id').notNull().references(() => atlasUser.id, { onDelete: 'cascade' }),
  title: text('title').notNull(),
  content: text('content').notNull(),
  category: text('category').notNull(),
  subcategory: text('subcategory').notNull(),
  sources: text('sources').notNull().default('[]'),
  images: text('images').notNull().default('[]'),
  annotations: text('annotations').notNull().default('[]'),
  createdAt: text('created_at').notNull(),
  updatedAt: text('updated_at').notNull(),
}, (table) => [index('atlas_entries_user_updated_idx').on(table.userId,table.updatedAt)]);

export const atlasSearchRate = sqliteTable('atlas_search_rate', {
  userId: text('user_id').primaryKey().references(() => atlasUser.id,{onDelete:'cascade'}),
  windowStart: integer('window_start').notNull(),
  count: integer('count').notNull(),
});
