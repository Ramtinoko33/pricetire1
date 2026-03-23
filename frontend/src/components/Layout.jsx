import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { LayoutDashboard, Upload, Database, FileText, Settings, Play } from 'lucide-react';

const Layout = ({ children }) => {
  const location = useLocation();

  const menuItems = [
    { path: '/', label: 'Dashboard', icon: LayoutDashboard },
    { path: '/upload', label: 'Upload', icon: Upload },
    { path: '/suppliers', label: 'Fornecedores', icon: Database },
    { path: '/results', label: 'Resultados', icon: FileText },
    { path: '/scraper', label: 'Scraper', icon: Play },
    { path: '/logs', label: 'Logs', icon: Settings },
  ];

  return (
    <div className="flex h-screen bg-slate-50" data-testid="app-layout">
      {/* Sidebar */}
      <aside className="w-64 bg-slate-900 text-slate-100 flex flex-col" data-testid="sidebar">
        <div className="p-6 border-b border-slate-700">
          <h1 className="text-xl font-bold tracking-tight" style={{ fontFamily: 'Chivo, sans-serif' }}>
            Pneu Price Scout
          </h1>
          <p className="text-xs text-slate-400 mt-1">Comparador B2B</p>
        </div>

        <nav className="flex-1 p-4" data-testid="nav-menu">
          {menuItems.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname === item.path;
            return (
              <Link
                key={item.path}
                to={item.path}
                data-testid={`nav-${item.label.toLowerCase()}`}
                className={`flex items-center gap-3 px-4 py-3 rounded-sm mb-1 transition-colors ${
                  isActive
                    ? 'bg-slate-800 text-white border-l-2 border-blue-500'
                    : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                }`}
              >
                <Icon size={18} />
                <span className="text-sm font-medium">{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="p-4 border-t border-slate-700 text-xs text-slate-400">
          <p>v1.0.0 MVP</p>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        <header className="bg-white border-b border-slate-200 px-8 py-4" data-testid="header">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-900" style={{ fontFamily: 'Chivo, sans-serif' }}>
              {menuItems.find(item => item.path === location.pathname)?.label || 'Pneu Price Scout'}
            </h2>
            <div className="text-sm text-slate-500">
              {new Date().toLocaleDateString('pt-PT', { weekday: 'long', day: 'numeric', month: 'long' })}
            </div>
          </div>
        </header>

        <div className="flex-1 overflow-auto p-8">
          {children}
        </div>
      </main>
    </div>
  );
};

export default Layout;
