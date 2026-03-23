import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Toaster } from 'sonner';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Upload from './pages/Upload';
import Suppliers from './pages/Suppliers';
import Results from './pages/Results';
import Logs from './pages/Logs';
import Scraper from './pages/Scraper';
import Precos from './pages/Precos';
import '@/App.css';

function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/upload" element={<Upload />} />
          <Route path="/suppliers" element={<Suppliers />} />
          <Route path="/results" element={<Results />} />
          <Route path="/scraper" element={<Scraper />} />
          <Route path="/precos" element={<Precos />} />
          <Route path="/logs" element={<Logs />} />
        </Routes>
      </Layout>
      <Toaster position="top-right" richColors />
    </BrowserRouter>
  );
}

export default App;
