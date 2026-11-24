import dayjs from 'dayjs';

export function formatDate(value: string | null | undefined): string {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-';
}

export function formatMoney(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '-';
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `¥${numeric.toFixed(2)}` : String(value);
}

export function statusColor(status: string): string {
  const colors: Record<string, string> = {
    ACTIVE: 'green',
    PUBLISHED: 'green',
    INDEXED: 'blue',
    PROCESSING: 'processing',
    PENDING_REVIEW: 'orange',
    CREATED: 'orange',
    UNSHIPPED: 'orange',
    SUCCESS: 'green',
    COMPLETED: 'green',
    DELIVERED: 'cyan',
    SHIPPED: 'blue',
    WAITING_RETURN: 'orange',
    RETURN_SHIPPED: 'blue',
    RECEIVED: 'cyan',
    FAILED: 'red',
    REJECTED: 'red',
    CANCELLED: 'default',
    CLOSED: 'default',
    DELETED: 'default',
    ARCHIVED: 'default',
    INACTIVE: 'default',
    DRAFT: 'default',
  };
  return colors[status] ?? 'default';
}
