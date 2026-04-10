import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Toaster } from 'sonner';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Comparar from './pages/Comparar';
import Suppliers from './pages/Suppliers';
import Results from './pages/Results';
import Logs from './pages/Logs';
import Precos from './pages/Precos';
import '@/App.css';

function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/comparar" element={<Comparar />} />
          <Route path="/suppliers" element={<Suppliers />} />
          <Route path="/results" element={<Results />} />
          <Route path="/scraper" element={<Precos />} />
          <Route path="/precos" element={<Precos />} />
          <Route path="/logs" element={<Logs />} />
        </Routes>
      </Layout>
      <Toaster position="top-right" richColors />
    </BrowserRouter>
  );
}

export default App;
