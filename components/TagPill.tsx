type TagPillProps = {
  value: string;
};

export function TagPill({ value }: TagPillProps) {
  return (
    <span className="inline-flex items-center rounded-full border border-blue-200 bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700">
      #{value}
    </span>
  );
}
