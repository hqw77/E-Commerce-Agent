import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { AppLoading } from '../components/Common';
import { useAuthStore } from '../stores/authStore';

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { status } = useAuthStore();
  const location = useLocation();

  if (status === 'idle' || status === 'loading') {
    return <AppLoading text="正在恢复登录状态…" />;
  }
  if (status !== 'authenticated') {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <>{children}</>;
}
