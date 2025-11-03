import { createHash } from "crypto";
import { eq } from "drizzle-orm";
import { DraftAction } from "@/types/agent";
import { db } from "@/lib/db";
import { agentActionLog } from "@/lib/schema";
import * as Notes from "@/server/tools/notes";
import { createWikiLinks, createSemanticLinks } from "@/lib/rag";

type CommitOptions = {
  userId: string;
};

function hashAction(action: DraftAction) {
  return createHash("sha256").update(JSON.stringify(action)).digest("hex");
}

export async function commitDraft(draft: DraftAction[], { userId }: CommitOptions) {
  const result = await db.transaction(async (tx) => {
    let applied = 0;
    const touchedNotes = new Set<string>();
    const contentByNote = new Map<string, string>();

    for (const action of draft) {
      const hash = hashAction(action);
      const logged = await tx.query.agentActionLog.findFirst({
        where: eq(agentActionLog.hash, hash),
        columns: { hash: true }
      });
      if (logged) continue;

      switch (action.type) {
        case "create_note": {
          const { id } = await Notes.createNote(action, tx);
          touchedNotes.add(id);
          contentByNote.set(id, action.content_md);
          break;
        }
        case "update_note": {
          const { mergedContent } = await Notes.updateNote(action, tx);
          touchedNotes.add(action.id);
          if (mergedContent) {
            contentByNote.set(action.id, mergedContent);
          }
          break;
        }
        case "add_link": {
          await Notes.addLink(action, tx);
          touchedNotes.add(action.from_id);
          break;
        }
        case "add_tag": {
          await Notes.addTag(action, tx);
          touchedNotes.add(action.note_id);
          break;
        }
        case "add_source": {
          await Notes.addSource(action, tx);
          touchedNotes.add(action.note_id);
          break;
        }
        default:
          break;
      }

      await tx.insert(agentActionLog).values({
        hash,
        userId,
        actionType: action.type,
        createdAt: new Date()
      });
      applied += 1;
    }

    return {
      applied,
      notesChanged: Array.from(touchedNotes),
      contentByNote
    };
  });

  await Promise.all(
    Array.from(result.contentByNote.entries()).map(async ([noteId, content]) => {
      await createWikiLinks(noteId, content);
      await createSemanticLinks(noteId);
    })
  );

  return {
    applied: result.applied,
    notesChanged: result.notesChanged
  };
}
