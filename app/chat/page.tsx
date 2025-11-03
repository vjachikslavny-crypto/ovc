import { ChatView } from "@/components/ChatView";

type ChatPageProps = {
  searchParams?: Record<string, string | string[] | undefined>;
};

export default function ChatPage({ searchParams }: ChatPageProps) {
  const prompt = typeof searchParams?.prompt === "string" ? searchParams?.prompt : undefined;
  const noteId =
    typeof searchParams?.noteId === "string" ? (searchParams?.noteId as string) : undefined;

  return (
    <section className="space-y-4">
      <ChatView initialMessage={prompt} initialNoteId={noteId} />
    </section>
  );
}
