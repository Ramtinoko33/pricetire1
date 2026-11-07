import React, { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'sonner';
import Layout from './components/Layout';
import { AuthProvider, RequireAdmin, RequireAuth } from './lib/auth';
import { TooltipProvider } from './components/ui/tooltip';
import { Spinner } from './components/common';
import Login from './pages/Login';
import '@/App.css';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const Comparar = lazy(() => import('./pages/Comparar'));
const Suppliers = lazy(() => import('./pages/Suppliers'));
const Results = lazy(() => import('./pages/Results'));
const Pesquisa = lazy(() => import('./pages/Pesquisa'));
const Catalogo = lazy(() => import('./pages/Catalogo'));
const Alertas = lazy(() => import('./pages/Alertas'));
const Operacao = lazy(() => import('./pages/Operacao'));
const Conta = lazy(() => import('./pages/Conta'));
const Admin = lazy(() => import('./pages/Admin'));

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/*"
        element={(
          <RequireAuth>
            <Layout>
              <Suspense fallback={<Spinner />}>
                <Routes>
                  <Route path="/" element={<Dashboard />} />
                  <Route path="/precos" element={<Pesquisa />} />
                  <Route path="/scraper" element={<Navigate to="/precos" replace />} />
                  <Route path="/comparar" element={<RequireAdmin><Comparar /></RequireAdmin>} />
                  <Route path="/catalogo" element={<RequireAdmin><Catalogo /></RequireAdmin>} />
                  <Route path="/alertas" element={<RequireAdmin><Alertas /></RequireAdmin>} />
                  <Route path="/results" element={<RequireAdmin><Results /></RequireAdmin>} />
                  <Route path="/suppliers" element={<RequireAdmin><Suppliers /></RequireAdmin>} />
                  <Route path="/operacao" element={<RequireAdmin><Operacao /></RequireAdmin>} />
                  <Route path="/logs" element={<Navigate to="/operacao" replace />} />
                  <Route path="/conta" element={<Conta />} />
                  <Route path="/admin" element={<RequireAdmin><Admin /></RequireAdmin>} />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </Suspense>
            </Layout>
          </RequireAuth>
        )}
      />
    </Routes>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <TooltipProvider delayDuration={200}>
          <AppRoutes />
        </TooltipProvider>
      </AuthProvider>
      <Toaster position="top-right" richColors />
    </BrowserRouter>
  );
}

export default App;
