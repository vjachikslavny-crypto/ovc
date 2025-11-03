type ReasonMeta = {
  label: string;
  badgeClass: string;
  stroke: string;
  nodeColor: string;
};

const defaults: ReasonMeta = {
  label: "Связь",
  badgeClass: "bg-slate-100 text-slate-700 border-slate-200",
  stroke: "#94a3b8",
  nodeColor: "#2563eb"
};

const registry: Record<string, ReasonMeta> = {
  semantic: {
    label: "Семантическая связь",
    badgeClass: "bg-violet-100 text-violet-700 border-violet-200",
    stroke: "#7c3aed",
    nodeColor: "#6d28d9"
  },
  wikilink: {
    label: "Вики-ссылка",
    badgeClass: "bg-blue-100 text-blue-700 border-blue-200",
    stroke: "#2563eb",
    nodeColor: "#1d4ed8"
  },
  user_request: {
    label: "Ручная связь",
    badgeClass: "bg-amber-100 text-amber-700 border-amber-200",
    stroke: "#f59e0b",
    nodeColor: "#d97706"
  },
  auto_child: {
    label: "Автосвязь",
    badgeClass: "bg-emerald-100 text-emerald-700 border-emerald-200",
    stroke: "#10b981",
    nodeColor: "#059669"
  },
  auto_fallback: {
    label: "Связь-подсказка",
    badgeClass: "bg-sky-100 text-sky-700 border-sky-200",
    stroke: "#0ea5e9",
    nodeColor: "#0284c7"
  }
};

export function getLinkReasonMeta(reason: string): ReasonMeta {
  return registry[reason] ?? defaults;
}

export const LINK_REASON_KEYS = Object.keys(registry);
