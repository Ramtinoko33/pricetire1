import React, { useEffect, useState } from 'react';
import { logsAPI } from '../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { RefreshCw } from 'lucide-react';
import { Button } from '../components/ui/button';
import { toast } from 'sonner';

const Logs = () => {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadLogs();
  }, []);

  const loadLogs = async () => {
    try {
      const { data } = await logsAPI.getAll();
      setLogs(data);
    } catch (error) {
      console.error('Error loading logs:', error);
      toast.error('Erro ao carregar logs');
    } finally {
      setLoading(false);
    }
  };

  const getLevelBadge = (level) => {
    const variants = {
      INFO: 'default',
      WARNING: 'secondary',
      ERROR: 'destructive',
    };
    return <Badge variant={variants[level] || 'outline'}>{level}</Badge>;
  };

  if (loading) {
    return <div className="text-center py-12" data-testid="loading">A carregar...</div>;
  }

  return (
    <div className="space-y-6" data-testid="logs-page">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold" style={{ fontFamily: 'Chivo, sans-serif' }}>Logs</h2>
          <p className="text-sm text-slate-600 mt-1">{logs.length} entradas</p>
        </div>
        <Button variant="outline" onClick={loadLogs} data-testid="refresh-logs-btn">
          <RefreshCw size={18} className="mr-2" />
          Atualizar
        </Button>
      </div>

      <Card className="border-slate-200">
        <CardContent className="p-0">
          {logs.length === 0 ? (
            <div className="text-center py-12 text-slate-500">Nenhum log encontrado</div>
          ) : (
            <div className="divide-y divide-slate-200">
              {logs.map((log) => (
                <div key={log.id} className="p-4 hover:bg-slate-50" data-testid={`log-${log.id}`}>
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        {getLevelBadge(log.level)}
                        <span className="text-xs text-slate-500 font-mono">
                          {new Date(log.created_at).toLocaleString('pt-PT')}
                        </span>
                        {log.supplier_id && (
                          <span className="text-xs text-slate-500">Supplier: {log.supplier_id.substring(0, 8)}</span>
                        )}
                        {log.job_id && (
                          <span className="text-xs text-slate-500">Job: {log.job_id.substring(0, 8)}</span>
                        )}
                      </div>
                      <p className="text-sm text-slate-700">{log.message}</p>
                      {log.screenshot_path && (
                        <p className="text-xs text-blue-600 mt-1">Screenshot: {log.screenshot_path}</p>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default Logs;
