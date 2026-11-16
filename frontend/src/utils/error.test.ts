import { describe, expect, it } from 'vitest';
import { ApiError } from '../api/client';
import { errorMessage } from './error';

describe('errorMessage', () => {
  it('maps permission and validation failures to Chinese messages', () => {
    expect(errorMessage(new ApiError('forbidden', 403))).toContain('权限');
    expect(errorMessage(new ApiError('bad request', 422))).toContain('参数');
    expect(errorMessage(new ApiError('rate limit', 429))).toContain('频繁');
  });

  it('keeps a backend business message for conflicts', () => {
    expect(errorMessage(new ApiError('订单状态冲突', 409))).toBe('订单状态冲突');
  });
});
