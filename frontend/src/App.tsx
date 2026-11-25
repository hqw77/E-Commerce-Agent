import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App as AntApp, ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { useEffect } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AdminLayout } from './layouts/AdminLayout';
import { DebugLayout } from './layouts/DebugLayout';
import { ShopLayout } from './layouts/ShopLayout';
import { AdminRoute } from './router/AdminRoute';
import { DebugRoute } from './router/DebugRoute';
import { ProtectedRoute } from './router/ProtectedRoute';
import { AppLoading } from './components/Common';
import { bootstrapAuth, useAuthStore } from './stores/authStore';
import { LoginPage } from './pages/auth/Login';
import { RegisterPage } from './pages/auth/Register';
import { DashboardPage } from './pages/dashboard/Dashboard';
import { ShopHomePage } from './pages/shop/ShopHome';
import { ShopProductPage } from './pages/shop/ShopProduct';
import { ShopOrdersPage } from './pages/shop/ShopOrders';
import { ShopOrderDetailPage } from './pages/shop/ShopOrderDetail';
import { ShopAfterSalesPage } from './pages/shop/ShopAfterSales';
import { ShopAfterSaleDetailPage } from './pages/shop/ShopAfterSaleDetail';
import { ShopApprovalsPage } from './pages/shop/ShopApprovals';
import { ProductListPage } from './pages/products/ProductList';
import { ProductDetailPage } from './pages/products/ProductDetail';
import { InventoryListPage } from './pages/inventory/InventoryList';
import { InventoryTransactionsPage } from './pages/inventory/InventoryTransactions';
import { OrderListPage } from './pages/orders/OrderList';
import { OrderDetailPage } from './pages/orders/OrderDetail';
import { AfterSaleListPage } from './pages/after-sales/AfterSaleList';
import { AfterSaleDetailPage } from './pages/after-sales/AfterSaleDetail';
import { KnowledgeListPage } from './pages/knowledge/KnowledgeList';
import { KnowledgeDetailPage } from './pages/knowledge/KnowledgeDetail';
import { AgentChatPage } from './pages/agent/AgentChat';
import { AgentApprovalsPage } from './pages/agent/AgentApprovals';
import { TraceConsolePage } from './pages/agent/TraceConsole';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function HomeRedirect() {
  const { status, user } = useAuthStore();

  if (status === 'idle' || status === 'loading') {
    return <AppLoading text="正在加载商城…" />;
  }
  if (status === 'authenticated' && user?.is_admin) {
    return <Navigate to="/dashboard" replace />;
  }
  if (status === 'authenticated' && user?.is_debugger) {
    return <Navigate to="/agent/debug" replace />;
  }
  return <Navigate to="/shop" replace />;
}

function AppRoutes() {
  const status = useAuthStore((state) => state.status);

  useEffect(() => {
    if (status === 'idle') void bootstrapAuth();
  }, [status]);

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/shop" element={<ShopLayout />}>
        <Route index element={<ShopHomePage />} />
        <Route path="products/:productNo" element={<ShopProductPage />} />
        <Route
          path="assistant"
          element={
            <ProtectedRoute>
              <AgentChatPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="orders"
          element={
            <ProtectedRoute>
              <ShopOrdersPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="orders/:orderNo"
          element={
            <ProtectedRoute>
              <ShopOrderDetailPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="after-sales"
          element={
            <ProtectedRoute>
              <ShopAfterSalesPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="after-sales/:afterSalesNo"
          element={
            <ProtectedRoute>
              <ShopAfterSaleDetailPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="approvals"
          element={
            <ProtectedRoute>
              <ShopApprovalsPage />
            </ProtectedRoute>
          }
        />
      </Route>
      <Route
        element={
          <AdminRoute>
            <AdminLayout />
          </AdminRoute>
        }
      >
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/products" element={<ProductListPage />} />
        <Route path="/products/:productId" element={<ProductDetailPage />} />
        <Route path="/inventory" element={<InventoryListPage />} />
        <Route path="/inventory/transactions" element={<InventoryTransactionsPage />} />
        <Route path="/orders" element={<OrderListPage />} />
        <Route path="/orders/:orderNo" element={<OrderDetailPage />} />
        <Route path="/after-sales" element={<AfterSaleListPage />} />
        <Route path="/after-sales/:afterSalesNo" element={<AfterSaleDetailPage />} />
        <Route path="/knowledge" element={<KnowledgeListPage />} />
        <Route path="/knowledge/:documentId" element={<KnowledgeDetailPage />} />
        <Route path="/agent" element={<AgentChatPage />} />
        <Route path="/agent/approvals" element={<AgentApprovalsPage />} />
      </Route>
      <Route
        element={
          <DebugRoute>
            <DebugLayout />
          </DebugRoute>
        }
      >
        <Route path="/agent/debug" element={<TraceConsolePage />} />
        <Route path="/agent/debug/chat" element={<AgentChatPage />} />
      </Route>
      <Route path="/" element={<HomeRedirect />} />
      <Route path="*" element={<Navigate to="/shop" replace />} />
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
