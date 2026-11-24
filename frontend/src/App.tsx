import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App as AntApp, ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { useEffect } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AdminLayout } from './layouts/AdminLayout';
import { ProtectedRoute } from './router/ProtectedRoute';
import { bootstrapAuth, useAuthStore } from './stores/authStore';
import { LoginPage } from './pages/auth/Login';
import { RegisterPage } from './pages/auth/Register';
import { DashboardPage } from './pages/dashboard/Dashboard';
import { ProductListPage } from './pages/products/ProductList';
import { ProductDetailPage } from './pages/products/ProductDetail';
import { CategoryListPage } from './pages/categories/CategoryList';
import { InventoryListPage } from './pages/inventory/InventoryList';
import { InventoryTransactionsPage } from './pages/inventory/InventoryTransactions';
import { OrderListPage } from './pages/orders/OrderList';
import { OrderDetailPage } from './pages/orders/OrderDetail';
import { AfterSaleListPage } from './pages/after-sales/AfterSaleList';
import { AfterSaleDetailPage } from './pages/after-sales/AfterSaleDetail';
import { KnowledgeListPage } from './pages/knowledge/KnowledgeList';
import { KnowledgeDetailPage } from './pages/knowledge/KnowledgeDetail';
import { AgentChatPage } from './pages/agent/AgentChat';
import { TraceConsolePage } from './pages/agent/TraceConsole';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function AppRoutes() {
  const status = useAuthStore((state) => state.status);

  useEffect(() => {
    if (status === 'idle') void bootstrapAuth();
  }, [status]);

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route
        element={
          <ProtectedRoute>
            <AdminLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/products" element={<ProductListPage />} />
        <Route path="/products/:productId" element={<ProductDetailPage />} />
        <Route path="/categories" element={<CategoryListPage />} />
        <Route path="/inventory" element={<InventoryListPage />} />
        <Route path="/inventory/transactions" element={<InventoryTransactionsPage />} />
        <Route path="/orders" element={<OrderListPage />} />
        <Route path="/orders/:orderNo" element={<OrderDetailPage />} />
        <Route path="/after-sales" element={<AfterSaleListPage />} />
        <Route path="/after-sales/:afterSalesNo" element={<AfterSaleDetailPage />} />
        <Route path="/knowledge" element={<KnowledgeListPage />} />
        <Route path="/knowledge/:documentId" element={<KnowledgeDetailPage />} />
        <Route path="/agent" element={<AgentChatPage />} />
        <Route path="/agent/debug" element={<TraceConsolePage />} />
      </Route>
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#3157d5',
          borderRadius: 8,
          fontFamily:
            'Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif',
        },
      }}
    >
      <AntApp>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <AppRoutes />
          </BrowserRouter>
        </QueryClientProvider>
      </AntApp>
    </ConfigProvider>
  );
}
