import { defineConfig } from "drizzle-kit";

export default defineConfig({
  schema: "./lib/schema.ts",
  out: "./drizzle",
  driver: "pg",
  dbCredentials: {
    connectionString:
      process.env.DATABASE_URL ||
      "postgres://postgres:postgres@localhost:5432/agent_notes"
  },
  verbose: true,
  strict: true
});
