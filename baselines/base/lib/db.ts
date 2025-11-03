import { drizzle } from "drizzle-orm/node-postgres";
import { Pool } from "pg";
import * as schema from "./schema";

declare global {
  // eslint-disable-next-line no-var
  var __dbPool: Pool | undefined;
}

if (!process.env.DATABASE_URL) {
  console.warn(
    "DATABASE_URL is not set. Database calls will fail until this is configured."
  );
}

const pool =
  globalThis.__dbPool ??
  new Pool({
    connectionString: process.env.DATABASE_URL
  });

if (process.env.NODE_ENV !== "production") {
  globalThis.__dbPool = pool;
}

export const db = drizzle(pool, { schema });

export type DbClient = typeof db;
