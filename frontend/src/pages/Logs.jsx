import React, { useEffect, useState, useRef } from 'react';
import { logsAPI } from '../lib/api';
import api from '../lib/api';
import { Card, CardContent } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { RefreshCw, ChevronDown, ChevronUp, AlertCircle, Info, AlertTriangle } from 'lucide-react';
import { Button } from '../components/ui/button';
import { toast } from 'sonner';

const LEVEL_CONFIG = {
  INFO:    { bg: 'bg-blue-500/10 dark:bg-blue-500/15',   border: 'border-l-4 border-blue-400',  badge: 'bg-blue-500/15 text-blue-700 dark:text-blue-300',   icon: <Info size={14} className="text-blue-500" /> },
  WARNING: { bg: 'bg-amber-500/10 dark:bg-amber-500/15', border: 'border-l-4 border-amber-400', badge: 'bg-amber-500/15 text-amber-700 dark:text-amber-300', icon: <AlertTriangle size={14} className="text-amber-500" /> },
  ERROR:   { bg: 'bg-red-500/10 dark:bg-red-500/15',     border: 'border-l-4 border-red-400',   badge: 'bg-red-500/15 text-red-700 dark:text-red-300',     icon: <AlertCircle size={14} className="text-red-500" /> },
};

const LogEntry = ({ log }) => {
  const [expanded, setExpanded] = useState(false);
  const cfg = LEVEL_CONFIG[log.level] || LEVEL_CONFIG.INFO;
  const isLong = log.message && log.message.length > 200;
  const displayMsg = isLong && !expanded ? log.message.slice(0, 200) + '...' : log.message;

  return (
    <div className={`p-3 ${cfg.bg} ${cfg.border} hover:brightness-95 transition-all`}>
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex-shrink-0">{cfg.icon}</div>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${cfg.badge}`}>{log.level}</span>
            <span className="text-xs text-muted-foreground font-mono">{new Date(log.created_at).toLocaleString('pt-PT')}</span>
            {log.job_id && <span className="text-xs text-muted-foreground font-mono">Job: {log.job_id.substring(0, 8)}</span>}
            {log.supplier_id && <span className="text-xs text-muted-foreground font-mono">Sup: {log.supplier_id.substring(0, 8)}</span>}
          </div>
          <pre className="text-xs text-foreground whitespace-pre-wrap break-all font-mono leading-relaxed">{displayMsg}</pre>
          {isLong && (
            <button onClick={() => setExpanded(!expanded)} className="text-xs text-blue-500 mt-1 flex items-center gap-1 hover:underline">
              {expanded ? <><ChevronUp size={12} /> Colapsar</> : <><ChevronDown size={12} /> Ver tudo ({log.message.length} chars)</>}
            </button>
          )}
          {log.screenshot_path && (
            <p className="text-xs text-blue-500 mt-1">📎 {log.screenshot_path}</p>
          )}
        </div>
      </div>
    </div>
  );
};

const Logs = () => {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [levelFilter, setLevelFilter] = useState('ALL');
  const [limit, setLimit] = useState(100);
  const [lastRefresh, setLastRefresh] = useState(null);
  const [search, setSearch] = useState('');
  const [schedStatus, setSchedStatus] = useState(null);
  const intervalRef = useRef(null);

  const loadSchedStatus = async () => {
    try {
      const { data } = await api.get('/scheduler-status');
      setSchedStatus(data && data.started_at ? data : null);
    } catch (e) {
      // silencioso — o cartão simplesmente não aparece
    }
  };

  const loadLogs = async (lim = limit) => {
    try {
      const { data } = await logsAPI.getAll(null, lim);
      setLogs(data);
    } catch (error) {
      console.error('Error loading logs:', error);
      toast.error('Erro ao carregar logs');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadLogs(); loadSchedStatus(); }, []);

  useEffect(() => {
    intervalRef.current = setInterval(() => {
      loadLogs();
      setLastRefresh(new Date());
    }, 30000);
    const onFocus = () => { loadLogs(); setLastRefresh(new Date()); };
    window.addEventListener('focus', onFocus);
    return () => {
      clearInterval(intervalRef.current);
      window.removeEventListener('focus', onFocus);
    };
  }, []);

  const handleLimitChange = (newLimit) => {
    setLimit(newLimit);
    loadLogs(newLimit);
  };

  const filtered = logs.filter(l => {
    const matchLevel = levelFilter === 'ALL' || l.level === levelFilter;
    const matchSearch = !search || l.message?.toLowerCase().includes(search.toLowerCase());
    return matchLevel && matchSearch;
  });

  const counts = { INFO: 0, WARNING: 0, ERROR: 0 };
  logs.forEach(l => { if (counts[l.level] !== undefined) counts[l.level]++; });

  if (loading) return <div className="text-center py-12">A carregar...</div>;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap justify-between items-center gap-3">
        <div>
          <h2 className="text-2xl font-bold" style={{ fontFamily: 'Chivo, sans-serif' }}>Logs</h2>
          <p className="text-xs text-muted-foreground mt-0.5">{filtered.length} de {logs.length} entradas{lastRefresh ? ` · actualizado ${lastRefresh.toLocaleTimeString('pt-PT')}` : ''}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="text"
            placeholder="Pesquisar..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="text-xs border border-border rounded px-2 py-1 w-40 bg-background text-foreground"
          />
          <select value={levelFilter} onChange={e => setLevelFilter(e.target.value)} className="text-xs border border-border rounded px-2 py-1 bg-background text-foreground">
            <option value="ALL">Todos ({logs.length})</option>
            <option value="INFO">INFO ({counts.INFO})</option>
            <option value="WARNING">WARNING ({counts.WARNING})</option>
            <option value="ERROR">ERROR ({counts.ERROR})</option>
          </select>
        </div>
      </div>

      {schedStatus && (
        <Card className="border-border bg-emerald-500/10">
          <CardContent className="p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-700 dark:text-emerald-300">
                SCRAPE AUTOMÁTICO
              </span>
              <span className="text-xs text-foreground">
                Início: <span className="font-mono">{new Date(schedStatus.started_at).toLocaleString('pt-PT')}</span>
              </span>
              <span className="text-xs text-foreground">
                Fim: <span className="font-mono">{schedStatus.finished_at ? new Date(schedStatus.finished_at).toLocaleString('pt-PT') : 'em curso...'}</span>
              </span>
            </div>
            {schedStatus.medidas && (
              <p className="text-xs text-muted-foreground mt-1">
                Medidas: <span className="font-mono">{schedStatus.medidas}</span>
                {schedStatus.num_suppliers ? ` · ${schedStatus.num_suppliers} fornecedores` : ''}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      <Card className="border-border">
        <CardContent className="p-0">
          {filtered.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground text-sm">Nenhum log encontrado</div>
          ) : (
            <div className="divide-y divide-border max-h-[70vh] overflow-y-auto">
              {filtered.map(log => <LogEntry key={log.id} log={log} />)}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default Logs;