import { formatStatus } from "@/lib/format";
import { useI18n } from "@/lib/i18n/provider";

export function StatusBadge({ status }: { status: string }) {
  const { t } = useI18n();
  return <span className={`statusBadge status-${status}`}>{formatStatus(status, t)}</span>;
}
