import { z } from "zod";

export const draftActionSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("create_note"),
    title: z.string().min(1),
    content_md: z.string().min(1)
  }),
  z.object({
    type: z.literal("update_note"),
    id: z.string().uuid(),
    patch_md: z.string().min(1),
    position: z.enum(["append", "prepend"])
  }),
  z.object({
    type: z.literal("add_link"),
    from_id: z.string().uuid(),
    to_title: z.string().min(1),
    reason: z.string().min(1),
    confidence: z.number().min(0).max(1)
  }),
  z.object({
    type: z.literal("add_source"),
    note_id: z.string().uuid(),
    source: z.object({
      url: z.string().url(),
      title: z.string().min(1),
      domain: z.string().min(1),
      published_at: z.string(),
      summary: z.string().min(1)
    })
  }),
  z.object({
    type: z.literal("add_tag"),
    note_id: z.string().uuid(),
    tag: z.string().min(1),
    weight: z.number().optional()
  })
]);

export type DraftAction = z.infer<typeof draftActionSchema>;
