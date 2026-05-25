import React, { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { LayoutDashboard, Scale, Database, FileText, Settings, Search, Moon, Sun } from 'lucide-react';

const Layout = ({ children }) => {
  const location = useLocation();
  const [dark, setDark] = useState(() => localStorage.getItem('theme') === 'dark');

  useEffect(() => {
    if (dark) {
      document.documentElement.classList.add('dark');
      localStorage.setItem('theme', 'dark');
    } else {
      document.documentElement.classList.remove('dark');
      localStorage.setItem('theme', 'light');
    }
  }, [dark]);

  const menuItems = [
    { path: '/', label: 'Dashboard', icon: LayoutDashboard },
    { path: '/comparar', label: 'Comparar', icon: Scale },
    { path: '/suppliers', label: 'Fornecedores', icon: Database },
    { path: '/results', label: 'Resultados', icon: FileText },
    { path: '/precos', label: 'Preços', icon: Search },
    { path: '/logs', label: 'Logs', icon: Settings },
  ];

  return (
    <div className="flex h-screen bg-background text-foreground" data-testid="app-layout">
      <aside className="w-64 bg-slate-900 dark:bg-zinc-900 text-slate-100 flex flex-col" data-testid="sidebar">
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
        <div className="p-4 border-t border-slate-700 flex items-center justify-between">
          <span className="text-xs text-slate-400">v1.0.0 MVP</span>
          <div className="flex items-center bg-slate-700/50 border border-slate-600 rounded-full p-1">
            <button
              onClick={() => setDark(false)}
              className={`flex items-center justify-center w-7 h-7 rounded-full transition-all ${
                !dark ? 'bg-white text-slate-900' : 'text-slate-400 hover:text-slate-200'
              }`}
              title="Modo claro"
            >
              <Sun size={14} />
            </button>
            <button
              onClick={() => setDark(true)}
              className={`flex items-center justify-center w-7 h-7 rounded-full transition-all ${
                dark ? 'bg-slate-600 text-white' : 'text-slate-400 hover:text-slate-200'
              }`}
              title="Modo escuro"
            >
              <Moon size={14} />
            </button>
          </div>
        </div>
      </aside>
      <main className="flex-1 flex flex-col overflow-hidden">
        <header className="bg-card border-b border-border px-8 py-4" data-testid="header">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100" style={{ fontFamily: 'Chivo, sans-serif' }}>
              {menuItems.find(item => item.path === location.pathname)?.label || 'Pneu Price Scout'}
            </h2>
            <div className="text-sm text-slate-500 dark:text-slate-400">
              {new Date().toLocaleDateString('pt-PT', { weekday: 'long', day: 'numeric', month: 'long' })}
            </div>
          </div>
        </header>
        <div className="flex-1 overflow-auto p-8 bg-background">
          {children}
        </div>
      </main>
    </div>
  );
};

export default Layout;