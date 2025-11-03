import { getLinkReasonMeta } from "./linkReasonMeta";

type LinkBadgeProps = {
  reason: string;
  confidence?: number | null;
};

export function LinkBadge({ reason, confidence }: LinkBadgeProps) {
  const meta = getLinkReasonMeta(reason);
  const confidenceText = typeof confidence === "number" ? ` · ${(confidence * 100).toFixed(0)}%` : "";

  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${meta.badgeClass}`}>
      {meta.label}
      {confidenceText}
    </span>
  );
}
