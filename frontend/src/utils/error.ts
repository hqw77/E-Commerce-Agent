import { ApiError } from '../api/client';

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) return '当前账号没有该操作权限';
    if (error.status === 404) return '资源不存在或无权访问';
    if (error.status === 409) return error.message || '业务状态冲突';
    if (error.status === 422) return '请求参数不符合要求';
    if (error.status === 429) return '请求过于频繁，请稍后再试';
    if (error.status === 503) return '服务暂时不可用，请稍后重试';
    if (error.status === 504) return '请求超时，请稍后重试';
    return error.message;
  }
  return error instanceof Error ? error.message : '请求失败';
}
