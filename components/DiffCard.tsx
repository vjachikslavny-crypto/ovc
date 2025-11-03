import type { DraftAction } from "@/lib/actions";
import { plainTextPreview } from "@/lib/markdown";

type Props = {
  action: DraftAction;
};

export function DiffCard({ action }: Props) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="text-xs font-medium uppercase tracking-wide text-gray-500">
        {labelFor(action.type)}
      </div>
      <div className="mt-2 text-sm text-gray-800">{renderDetails(action)}</div>
    </div>
  );
}

function labelFor(type: DraftAction["type"]) {
  switch (type) {
    case "create_note":
      return "Создание заметки";
    case "update_note":
      return "Обновление заметки";
    case "add_link":
      return "Связь";
    case "add_source":
      return "Источник";
    case "add_tag":
      return "Тег";
    default:
      return type;
  }
}

function renderDetails(action: DraftAction) {
  switch (action.type) {
    case "create_note":
      return (
        <div>
          <div className="font-medium">{action.title}</div>
          <p className="mt-1 text-gray-600">{plainTextPreview(action.content_md)}</p>
        </div>
      );
    case "update_note":
      return (
        <div>
          <div className="text-gray-600">
            {action.position === "append" ? "Добавить в конец" : "Добавить в начало"}
          </div>
          <p className="mt-1 text-gray-800">
            {plainTextPreview(action.patch_md, 120)}
          </p>
        </div>
      );
    case "add_link":
      return (
        <div className="flex flex-col gap-1">
          <span>
            Связать заметку с <strong>{action.to_title}</strong>
          </span>
          <span className="text-gray-600">
            Причина: {action.reason}, уверенность {Math.round(action.confidence * 100)}%
          </span>
        </div>
      );
    case "add_source":
      return (
        <div className="flex flex-col gap-1">
          <span className="font-medium">{action.source.title}</span>
          <span className="text-gray-600">{action.source.domain}</span>
          <p className="text-gray-700">{action.source.summary}</p>
        </div>
      );
    case "add_tag":
      return (
        <div>
          <span className="font-medium">#{action.tag}</span>
          {action.weight && (
            <span className="ml-2 text-xs text-gray-500">
              вес {action.weight.toFixed(1)}
            </span>
          )}
        </div>
      );
    default:
      return null;
  }
}
