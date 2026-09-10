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
  return (
    <div className="stat-tile">
      <div className="stat-tile__label">{label}</div>
      <div className={`stat-tile__value ${TONE_CLASS[tone]}`}>{value}</div>
    </div>
  );
}
