import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { AppLoading } from '../components/Common';
import { useAuthStore } from '../stores/authStore';

export function AdminRoute({ children }: { children: ReactNode }) {
  const { status, user } = useAuthStore();
  const location = useLocation();

  if (status === 'idle' || status === 'loading') {
    return <AppLoading text="正在恢复登录状态…" />;
  }
  if (status !== 'authenticated' || !user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  if (!user.is_admin) {
    return <Navigate to="/shop" replace />;
  }
  return <>{children}</>;
}
