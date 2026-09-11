type Tone = "default" | "success" | "warning" | "danger";

const TONE_CLASS: Record<Tone, string> = {
  default: "",
  success: "stat-tile__value--success",
  warning: "stat-tile__value--warning",
  danger: "stat-tile__value--danger",
};

export function StatTile({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: number;
  tone?: Tone;
}) {
  // Zero must stay neutral so it is not read as “risk red / warning”.
  const effectiveTone: Tone = value === 0 ? "default" : tone;
  return (
    <div className="stat-tile">
      <div className="stat-tile__label">{label}</div>
      <div className={`stat-tile__value ${TONE_CLASS[effectiveTone]}`}>{value}</div>
    </div>
  );
}
