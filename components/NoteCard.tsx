import Link from "next/link";
import { plainTextPreview } from "@/lib/markdown";
import { TagPill } from "./TagPill";

type NotePreview = {
  id: string;
  title: string;
  contentMd: string;
  tags?: string[];
  updatedAt?: Date;
};

export function NoteCard({ id, title, contentMd, tags, updatedAt }: NotePreview) {
  return (
    <Link
      href={`/n/${id}`}
      className="flex flex-col gap-2 rounded-lg border border-gray-200 bg-white p-4 shadow-sm transition hover:border-blue-400 hover:shadow-md"
    >
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-lg font-semibold text-gray-800">{title}</h3>
        {updatedAt && (
          <span className="text-xs text-gray-500">
            {updatedAt.toLocaleDateString()}
          </span>
        )}
      </div>
      <p className="text-sm text-gray-600">{plainTextPreview(contentMd, 160)}</p>
      {tags && tags.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {tags.map((tag) => (
            <TagPill key={tag} value={tag} />
          ))}
        </div>
      )}
    </Link>
  );
}
