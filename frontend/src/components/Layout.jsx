import React, { useState, useEffect, useRef } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, Scale, Database, FileText, Search, Moon, Sun, Menu, X, BookOpen,
  Bell, Activity, ShieldCheck, LogOut, UserCircle, ChevronDown, Users, Tag, CalendarClock,
} from 'lucide-react';
import { useAuth } from '@/lib/auth';
import { cn } from '@/lib/utils';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from './ui/dropdown-menu';

// Cliente identificado no README do projecto.
const WORKSPACE_NAME = 'Oficinas D. Pedro V';
const DESKTOP_QUERY = '(min-width: 1024px)';

function readTheme() {
  try {
    return window.localStorage.getItem('theme') === 'dark';
  } catch {
    return false;
  }
}

function useMediaQuery(query) {
  const get = () => (typeof window !== 'undefined' && window.matchMedia ? window.matchMedia(query).matches : true);
  const [matches, setMatches] = useState(get);
  useEffect(() => {
    if (!window.matchMedia) return undefined;
    const mql = window.matchMedia(query);
    const onChange = () => setMatches(mql.matches);
    onChange();
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, [query]);
  return matches;
}

// O perfil "utilizador" só vê Dashboard e Pesquisa; o resto é de administradores.
export const MENU_ITEMS = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/precos', label: 'Pesquisa', icon: Search, aliases: ['/scraper'] },
  { path: '/catalogo', label: 'Stock permanente', icon: BookOpen, adminOnly: true },
  { path: '/comparar', label: 'Campanhas', icon: Scale, adminOnly: true },
  { path: '/results', label: 'Histórico de campanhas', icon: FileText, adminOnly: true },
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

const ROLE_LABELS = { admin: 'Administrador', user: 'Utilizador', utilizador: 'Utilizador' };

function NavLink({ item, active, child = false }) {
  const Icon = item.icon;
  return (
    <Link
      to={item.path}
      data-testid={`nav-${item.path.replace('/', '') || 'dashboard'}`}
      aria-current={active ? 'page' : undefined}
      className={cn(
        'flex items-center gap-3 rounded-lg px-3 text-[13.5px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-foreground/70 focus-visible:ring-offset-0',
        child ? 'py-2' : 'py-2.5',
        active
          ? 'bg-sidebar-accent font-bold text-sidebar-accent-foreground'
          : 'font-medium text-sidebar-foreground/90 hover:bg-sidebar-hover hover:text-sidebar-foreground',
      )}
    >
      {!child && <Icon size={18} strokeWidth={1.7} aria-hidden="true" className="flex-shrink-0" />}
      <span className="min-w-0 leading-snug">{item.label}</span>
    </Link>
  );
}

const Layout = ({ children }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, isAdmin, logout } = useAuth();
  const [dark, setDark] = useState(readTheme);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const isDesktop = useMediaQuery(DESKTOP_QUERY);
  const toggleRef = useRef(null);
  const closeRef = useRef(null);
  const wasOpen = useRef(false);

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
    if (isDesktop) setDrawerOpen(false);
  }, [isDesktop]);

  useEffect(() => {
    if (!drawerOpen) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') setDrawerOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [drawerOpen]);

  // Foco: entra no menu ao abrir e regressa ao botão ao fechar.
  useEffect(() => {
    if (drawerOpen) closeRef.current?.focus();
    else if (wasOpen.current) toggleRef.current?.focus();
    wasOpen.current = drawerOpen;
  }, [drawerOpen]);

  const items = MENU_ITEMS.filter((i) => !i.adminOnly || isAdmin);
  const isActive = (item) => location.pathname === item.path || (item.aliases || []).includes(location.pathname);
  const current = flatItems(items).find(isActive);
  const adminGroupActive = items.some((i) => i.children?.some(isActive));
  const [adminOpen, setAdminOpen] = useState(true);
  useEffect(() => { if (adminGroupActive) setAdminOpen(true); }, [adminGroupActive]);
  const title = current?.label || EXTRA_TITLES[location.pathname] || 'Pneu Price Scout';
  const parentGroup = items.find((i) => i.children?.some(isActive));
  const displayName = user?.name || user?.email || '';
  const initial = (displayName.trim()[0] || '?').toUpperCase();
  const roleLabel = ROLE_LABELS[user?.role] || user?.role;
  const sidebarHidden = !isDesktop && !drawerOpen;

  const handleLogout = () => {
    logout();
    navigate('/login', { replace: true });
  };

  return (
    <div className="flex h-screen bg-background text-foreground" data-testid="app-layout">
      <a href="#conteudo" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-card focus:px-3 focus:py-2 focus:text-sm focus:font-semibold focus:text-primary focus:shadow-overlay">
        Saltar para o conteúdo
      </a>
      {drawerOpen && (
        <div
          className="fixed inset-0 z-30 bg-slate-950/55 lg:hidden"
          onClick={() => setDrawerOpen(false)}
          aria-hidden="true"
        />
      )}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 flex w-[248px] max-w-[85vw] flex-col bg-sidebar text-sidebar-foreground border-r border-sidebar-border transition-transform duration-200 lg:static lg:w-[228px] lg:translate-x-0',
          drawerOpen ? 'translate-x-0 shadow-modal' : '-translate-x-full',
        )}
        data-testid="sidebar"
        aria-label="Menu principal"
        inert={sidebarHidden ? true : undefined}
        aria-hidden={sidebarHidden ? true : undefined}
      >
        <div className="flex items-start justify-between px-6 pb-6 pt-7">
          <div>
            <p className="text-[17px] font-extrabold leading-tight tracking-[-0.03em]">Pneu Price Scout</p>
            <p className="mt-1.5 text-[11px] font-medium uppercase tracking-[0.06em] text-sidebar-muted">Comparador B2B</p>
          </div>
          <button
            ref={closeRef}
            className="lg:hidden -mr-2 -mt-1 rounded-md p-2 text-sidebar-muted hover:bg-sidebar-hover hover:text-sidebar-foreground"
            onClick={() => setDrawerOpen(false)}
            aria-label="Fechar menu"
          >
            <X size={20} />
          </button>
        </div>
        <nav className="flex-1 overflow-y-auto px-4 pb-4" data-testid="nav-menu" aria-label="Navegação principal">
          <div className="space-y-1">
            {items.filter((i) => !i.children).map((item) => (
              <NavLink key={item.path} item={item} active={isActive(item)} />
            ))}
          </div>
          {items.filter((i) => i.children).map((item) => (
            <div key={item.key} className="mt-6">
              <button
                type="button"
                onClick={() => setAdminOpen((o) => !o)}
                aria-expanded={adminOpen}
                data-testid={`nav-group-${item.key}`}
                className="flex w-full items-center justify-between rounded-md px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.1em] text-sidebar-muted hover:text-sidebar-foreground"
              >
                {item.label}
                <ChevronDown size={14} className={cn('transition-transform', !adminOpen && '-rotate-90')} aria-hidden="true" />
              </button>
              {adminOpen && (
                <div className="mt-1.5 space-y-0.5">
                  {item.children.map((c) => <NavLink key={c.path} item={c} active={isActive(c)} child />)}
                </div>
              )}
            </div>
          ))}
        </nav>
        <div className="flex items-center justify-between border-t border-sidebar-border px-5 py-4">
          <span className="text-[11px] text-sidebar-muted">v2.0</span>
          <div className="flex items-center rounded-full border border-sidebar-border bg-sidebar-hover/60 p-0.5" role="group" aria-label="Tema">
            <button
              onClick={() => setDark(false)}
              className={cn('flex h-7 w-7 items-center justify-center rounded-full transition-colors',
                !dark ? 'bg-sidebar-foreground text-sidebar' : 'text-sidebar-muted hover:text-sidebar-foreground')}
              title="Modo claro"
              aria-label="Modo claro"
              aria-pressed={!dark}
            >
              <Sun size={14} />
            </button>
            <button
              onClick={() => setDark(true)}
              className={cn('flex h-7 w-7 items-center justify-center rounded-full transition-colors',
                dark ? 'bg-sidebar-foreground text-sidebar' : 'text-sidebar-muted hover:text-sidebar-foreground')}
              title="Modo escuro"
              aria-label="Modo escuro"
              aria-pressed={dark}
            >
              <Moon size={14} />
            </button>
          </div>
        </div>
      </aside>
      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex h-14 sm:h-16 flex-shrink-0 items-center border-b border-border bg-card px-4 sm:px-8" data-testid="header">
          <div className="flex w-full items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-2">
              <button
                ref={toggleRef}
                className="lg:hidden -ml-2 flex h-11 w-11 items-center justify-center rounded-lg hover:bg-muted"
                onClick={() => setDrawerOpen(true)}
                aria-label="Abrir menu"
                aria-expanded={drawerOpen}
                data-testid="menu-toggle"
              >
                <Menu size={20} />
              </button>
              <nav aria-label="Localização" className="min-w-0">
                <ol className="flex min-w-0 items-center gap-1.5 text-[13px] text-muted-foreground">
                  <li className="hidden sm:block whitespace-nowrap">{WORKSPACE_NAME}</li>
                  <li className="hidden sm:block" aria-hidden="true">/</li>
                  {parentGroup && <li className="hidden md:block whitespace-nowrap">{parentGroup.label}</li>}
                  {parentGroup && <li className="hidden md:block" aria-hidden="true">/</li>}
                  <li className="truncate font-semibold text-foreground sm:font-medium" aria-current="page">{title}</li>
                </ol>
              </nav>
            </div>
            <div className="flex items-center gap-3">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button className="flex items-center gap-2.5 rounded-lg px-1.5 py-1 text-[13px] hover:bg-muted" data-testid="user-menu" aria-label={`Conta: ${displayName}`}>
                    <span aria-hidden="true" className="grid h-8 w-8 flex-shrink-0 place-items-center rounded-full bg-accent text-[13px] font-bold text-accent-foreground">{initial}</span>
                    <span className="hidden sm:flex max-w-[180px] flex-col items-start leading-tight">
                      <span className="max-w-full truncate font-semibold">{displayName}</span>
                      {roleLabel && <span className="text-[11px] text-muted-foreground">{roleLabel}</span>}
                    </span>
                    <ChevronDown size={14} className="hidden sm:inline text-muted-foreground" />
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
          <div className="bg-warning-subtle text-warning text-xs px-4 py-1 text-center" data-testid="mock-banner">
            Modo demonstração: API simulada com dados fictícios (VITE_USE_MOCK=1)
          </div>
        )}
        <div className="flex-1 overflow-auto bg-background">
          <div id="conteudo" tabIndex={-1} className="mx-auto w-full max-w-[1600px] px-4 py-6 focus:outline-none sm:px-6 lg:px-8 lg:py-8">
            {children}
          </div>
        </div>
      </main>
    </div>
  );
};

export default Layout;
