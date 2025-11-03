import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type SourceItem = {
  id?: string;
  url: string;
  domain: string;
  title: string;
  publishedAt?: Date | string | null;
  summary: string;
};

type Props = {
  sources: SourceItem[];
};

export function SourcesTable({ sources }: Props) {
  if (sources.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-gray-300 p-4 text-sm text-gray-500">
        Источники пока не добавлены. Попросите агента найти свежие материалы.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-md border border-gray-200">
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-2 text-left font-medium text-gray-500">Источник</th>
            <th className="px-4 py-2 text-left font-medium text-gray-500">Дата</th>
            <th className="px-4 py-2 text-left font-medium text-gray-500">Описание</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200 bg-white">
          {sources.map((source) => (
            <tr key={source.id ?? source.url}>
              <td className="px-4 py-2">
                <div className="flex flex-col">
                  <a
                    href={source.url}
                    target="_blank"
                    rel="noreferrer"
                    className="font-medium text-blue-600 hover:underline"
                  >
                    {source.title}
                  </a>
                  <span className="text-xs text-gray-500">{source.domain}</span>
                </div>
              </td>
              <td className="px-4 py-2 text-xs text-gray-500">
                {source.publishedAt
                  ? new Date(source.publishedAt).toLocaleDateString()
                  : "—"}
              </td>
              <td className="px-4 py-2 text-gray-700">
                <ReactMarkdown remarkPlugins={[remarkGfm]} className="prose prose-sm max-w-none">
                  {source.summary || "—"}
                </ReactMarkdown>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
