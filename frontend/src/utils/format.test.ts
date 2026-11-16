import { describe, expect, it } from 'vitest';
import { formatDate, formatMoney, statusColor } from './format';

describe('format helpers', () => {
  it('formats money without losing the BigDecimal string value', () => {
    expect(formatMoney('19.90')).toBe('¥19.90');
    expect(formatMoney(null)).toBe('-');
  });

  it('formats dates and handles null', () => {
    expect(formatDate(null)).toBe('-');
    expect(formatDate('2026-11-16T10:00:00')).toContain('2026-11-16');
  });

  it('maps backend statuses to semantic colors', () => {
    expect(statusColor('PENDING_PAYMENT')).toBe('orange');
    expect(statusColor('ACTIVE')).toBe('green');
    expect(statusColor('UNKNOWN')).toBe('default');
  });
});
