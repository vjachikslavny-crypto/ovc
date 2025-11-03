import Link from "next/link";
import { LinkBadge } from "./LinkBadge";

export type ConnectionItem = {
  id: string;
  title: string;
  reason: string;
  confidence?: number | null;
};

type ConnectionsPanelProps = {
  outbound: ConnectionItem[];
  inbound: ConnectionItem[];
};

export function ConnectionsPanel({ outbound, inbound }: ConnectionsPanelProps) {
  const hasConnections = outbound.length > 0 || inbound.length > 0;

  return (
    <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
      <div className="border-b border-gray-200 px-4 py-3">
        <h3 className="text-sm font-semibold text-gray-700">Связи</h3>
        <p className="mt-1 text-xs text-gray-500">
          Внешние и обратные ссылки помогают агенту строить граф знаний.
        </p>
      </div>
      {hasConnections ? (
        <div className="grid gap-0 border-t border-gray-100 md:grid-cols-2">
          <ConnectionColumn
            title="Исходит"
            items={outbound}
            emptyMessage="Здесь появятся заметки, на которые ссылается текущая."
            hasDivider
          />
          <ConnectionColumn
            title="Ведёт к заметке"
            items={inbound}
            emptyMessage="Пока нет заметок, которые ссылались бы сюда."
          />
        </div>
      ) : (
        <div className="px-4 py-6 text-sm text-gray-500">
          Связей пока нет. Попросите агента добавить контекст или объединить заметки.
        </div>
      )}
    </div>
  );
}

type ColumnProps = {
  title: string;
  items: ConnectionItem[];
  emptyMessage: string;
  hasDivider?: boolean;
};

function ConnectionColumn({ title, items, emptyMessage, hasDivider = false }: ColumnProps) {
  return (
    <div className={`border-gray-100 px-4 py-4 ${hasDivider ? "md:border-r" : ""}`}>
      <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500">{title}</h4>
      <ul className="mt-3 space-y-3">
        {items.length > 0 ? (
          items.map((item) => (
            <li key={item.id} className="rounded-md border border-gray-200 px-3 py-2 shadow-sm transition hover:border-blue-300 hover:shadow">
              <Link href={`/n/${item.id}`} className="flex flex-col gap-1">
                <span className="text-sm font-medium text-gray-800">{item.title}</span>
                <LinkBadge reason={item.reason} confidence={item.confidence} />
              </Link>
            </li>
          ))
        ) : (
          <li className="text-sm text-gray-500">{emptyMessage}</li>
        )}
      </ul>
    </div>
  );
}
