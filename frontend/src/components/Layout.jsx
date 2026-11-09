import React, { useState, useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, Scale, Database, FileText, Search, Moon, Sun, Menu, X, BookOpen,
  Bell, Activity, ShieldCheck, LogOut, UserCircle, ChevronDown, ChevronRight, Users, Tag, CalendarClock,
} from 'lucide-react';
import { useAuth } from '@/lib/auth';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from './ui/dropdown-menu';

function readTheme() {
  try {
    return window.localStorage.getItem('theme') === 'dark';
  } catch {
    return false;
  }
}

// O perfil "utilizador" só vê Dashboard e Pesquisa; o resto é de administradores.
export const MENU_ITEMS = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/precos', label: 'Pesquisa', icon: Search, aliases: ['/scraper'] },
  { path: '/catalogo', label: 'Catálogo', icon: BookOpen, adminOnly: true },
  { path: '/comparar', label: 'Comparar', icon: Scale, adminOnly: true },
  { path: '/results', label: 'Resultados', icon: FileText, adminOnly: true },
  {
    key: 'admin', label: 'Administração', icon: ShieldCheck, adminOnly: true,
    children: [
      { path: '/admin', label: 'Utilizadores', icon: Users },
      { path: '/suppliers', label: 'Fornecedores', icon: Database },
      { path: '/marcas', label: 'Marcas', icon: Tag },
      { path: '/monitorizacao', label: 'Medidas monitorizadas', icon: CalendarClock },
      { path: '/operacao', label: 'Operação', icon: Activity, aliases: ['/logs'] },
      { path: '/alertas', label: 'Alertas', icon: Bell },
    ],
  },
];

const flatItems = (list) => list.flatMap((i) => (i.children ? i.children : [i]));

const EXTRA_TITLES = { '/conta': 'Conta' };

function NavLink({ item, active, small = false }) {
  const Icon = item.icon;
  return (
    <Link
      to={item.path}
      data-testid={`nav-${item.path.replace('/', '') || 'dashboard'}`}
      className={`flex items-center gap-3 px-4 ${small ? 'py-2' : 'py-3'} rounded-sm mb-1 transition-colors ${
        active
          ? 'bg-slate-800 text-white border-l-2 border-blue-500'
          : 'text-slate-300 hover:bg-slate-800 hover:text-white'
      }`}
    >
      <Icon size={small ? 16 : 18} />
      <span className="text-sm font-medium">{item.label}</span>
    </Link>
  );
}

const Layout = ({ children }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, isAdmin, logout } = useAuth();
  const [dark, setDark] = useState(readTheme);
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark);
    try {
      window.localStorage.setItem('theme', dark ? 'dark' : 'light');
    } catch {
      /* storage indisponível */
    }
  }, [dark]);

  useEffect(() => {
    setDrawerOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!drawerOpen) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') setDrawerOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [drawerOpen]);

  const items = MENU_ITEMS.filter((i) => !i.adminOnly || isAdmin);
  const isActive = (item) => location.pathname === item.path || (item.aliases || []).includes(location.pathname);
  const current = flatItems(items).find(isActive);
  const adminGroupActive = items.some((i) => i.children?.some(isActive));
  const [adminOpen, setAdminOpen] = useState(adminGroupActive);
  useEffect(() => { if (adminGroupActive) setAdminOpen(true); }, [adminGroupActive]);
  const title = current?.label || EXTRA_TITLES[location.pathname] || 'Pneu Price Scout';

  const handleLogout = () => {
    logout();
    navigate('/login', { replace: true });
  };

  return (
    <div className="flex h-screen bg-background text-foreground" data-testid="app-layout">
      {drawerOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/50 lg:hidden"
          onClick={() => setDrawerOpen(false)}
          aria-hidden="true"
        />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-40 w-64 max-w-[85vw] bg-slate-900 dark:bg-zinc-900 text-slate-100 flex flex-col transform transition-transform duration-200 lg:static lg:translate-x-0 ${
          drawerOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
        data-testid="sidebar"
        aria-label="Menu principal"
      >
        <div className="p-6 border-b border-slate-700 flex items-start justify-between">
          <div>
            <h1 className="text-xl font-bold tracking-tight" style={{ fontFamily: 'Chivo, sans-serif' }}>
              Pneu Price Scout
            </h1>
            <p className="text-xs text-slate-400 mt-1">Comparador B2B</p>
          </div>
          <button
            className="lg:hidden text-slate-400 hover:text-white p-1"
            onClick={() => setDrawerOpen(false)}
            aria-label="Fechar menu"
          >
            <X size={20} />
          </button>
        </div>
        <nav className="flex-1 p-4 overflow-y-auto" data-testid="nav-menu">
          {items.map((item) => {
            const Icon = item.icon;
            if (item.children) {
              const Chevron = adminOpen ? ChevronDown : ChevronRight;
              return (
                <div key={item.key} className="mb-1">
                  <button
                    type="button"
                    onClick={() => setAdminOpen((o) => !o)}
                    aria-expanded={adminOpen}
                    data-testid={`nav-group-${item.key}`}
                    className={`w-full flex items-center gap-3 px-4 py-3 rounded-sm transition-colors ${
                      adminGroupActive ? 'text-white' : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                    }`}
                  >
                    <Icon size={18} />
                    <span className="text-sm font-medium flex-1 text-left">{item.label}</span>
                    <Chevron size={14} />
                  </button>
                  {adminOpen && (
                    <div className="ml-4 border-l border-slate-700 pl-2">
                      {item.children.map((c) => <NavLink key={c.path} item={c} active={isActive(c)} small />)}
                    </div>
                  )}
                </div>
              );
            }
            return <NavLink key={item.path} item={item} active={isActive(item)} />;
          })}
        </nav>
        <div className="p-4 border-t border-slate-700 flex items-center justify-between">
          <span className="text-xs text-slate-400">v2.0</span>
          <div className="flex items-center bg-slate-700/50 border border-slate-600 rounded-full p-1">
            <button
              onClick={() => setDark(false)}
              className={`flex items-center justify-center w-7 h-7 rounded-full transition-all ${
                !dark ? 'bg-white text-slate-900' : 'text-slate-400 hover:text-slate-200'
              }`}
              title="Modo claro"
              aria-label="Modo claro"
            >
              <Sun size={14} />
            </button>
            <button
              onClick={() => setDark(true)}
              className={`flex items-center justify-center w-7 h-7 rounded-full transition-all ${
                dark ? 'bg-slate-600 text-white' : 'text-slate-400 hover:text-slate-200'
              }`}
              title="Modo escuro"
              aria-label="Modo escuro"
            >
              <Moon size={14} />
            </button>
          </div>
        </div>
      </aside>
      <main className="flex-1 flex flex-col overflow-hidden min-w-0">
        <header className="bg-card border-b border-border px-4 sm:px-8 py-3 sm:py-4" data-testid="header">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3 min-w-0">
              <button
                className="lg:hidden p-2 -ml-2 rounded-md hover:bg-muted"
                onClick={() => setDrawerOpen(true)}
                aria-label="Abrir menu"
                data-testid="menu-toggle"
              >
                <Menu size={20} />
              </button>
              <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100 truncate" style={{ fontFamily: 'Chivo, sans-serif' }}>
                {title}
              </h2>
            </div>
            <div className="flex items-center gap-4">
              <div className="hidden md:block text-sm text-slate-500 dark:text-slate-400">
                {new Date().toLocaleDateString('pt-PT', { weekday: 'long', day: 'numeric', month: 'long' })}
              </div>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-muted text-sm" data-testid="user-menu">
                    <UserCircle size={20} />
                    <span className="hidden sm:inline max-w-[160px] truncate">{user?.name || user?.email}</span>
                    <ChevronDown size={14} className="hidden sm:inline" />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-56">
                  <DropdownMenuLabel>
                    <div className="truncate">{user?.name || '—'}</div>
                    <div className="text-xs font-normal text-muted-foreground truncate">{user?.email}</div>
                    {user?.role && <div className="text-xs font-normal text-muted-foreground">Perfil: {user.role}</div>}
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onSelect={() => navigate('/conta')}>
                    <UserCircle size={14} className="mr-2" /> Conta
                  </DropdownMenuItem>
                  {isAdmin && (
                    <DropdownMenuItem onSelect={() => navigate('/admin')}>
                      <ShieldCheck size={14} className="mr-2" /> Administração
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onSelect={handleLogout} data-testid="logout">
                    <LogOut size={14} className="mr-2" /> Terminar sessão
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        </header>
        {__USE_MOCK__ && (
          <div className="bg-amber-100 text-amber-900 dark:bg-amber-500/20 dark:text-amber-200 text-xs px-4 py-1 text-center" data-testid="mock-banner">
            Modo demonstração: API simulada com dados fictícios (VITE_USE_MOCK=1)
          </div>
        )}
        <div className="flex-1 overflow-auto p-4 sm:p-6 lg:p-8 bg-background">
          {children}
        </div>
      </main>
    </div>
  );
};

export default Layout;
