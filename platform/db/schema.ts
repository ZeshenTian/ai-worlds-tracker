import { sqliteTable, text } from "drizzle-orm/sqlite-core";

export const submissions = sqliteTable("submissions", {
  id: text("id").primaryKey(),
  title: text("title").notNull(),
  source: text("source").notNull(),
  sourceKey: text("source_key").notNull().unique(),
  demo: text("demo"),
  repo: text("repo"),
  theme: text("theme").notNull(),
  notes: text("notes"),
  status: text("status", { enum: ["pending", "approved", "rejected"] }).notNull().default("pending"),
  createdAt: text("created_at").notNull(),
});
