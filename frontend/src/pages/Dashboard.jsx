import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { statsAPI, jobsAPI } from '../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { TrendingUp, Package, CheckCircle, Database } from 'lucide-react';
import { Badge } from '../components/ui/badge';

const Dashboard = () => {
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadStats();
  }, []);

  const loadStats = async () => {
    try {
      const { data } = await statsAPI.getDashboard();
      setStats(data);
    } catch (error) {
      console.error('Error loading stats:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="text-center py-12" data-testid="loading">A carregar...</div>;
  }

  const statCards = [
    {
      title: 'Economia Total',
      value: `€${stats?.total_savings?.toFixed(2) || '0.00'}`,
      icon: TrendingUp,
      color: 'text-green-600 dark:text-green-400',
      bg: 'bg-green-100 dark:bg-green-900/30',
    },
    {
      title: 'Jobs Completos',
      value: stats?.completed_jobs || 0,
      icon: CheckCircle,
      color: 'text-blue-600 dark:text-blue-400',
      bg: 'bg-blue-100 dark:bg-blue-900/30',
    },
    {
      title: 'Total Jobs',
      value: stats?.total_jobs || 0,
      icon: Package,
      color: 'text-foreground',
      bg: 'bg-muted',
    },
    {
      title: 'Fornecedores Ativos',
      value: stats?.active_suppliers || 0,
      icon: Database,
      color: 'text-indigo-600 dark:text-indigo-400',
      bg: 'bg-indigo-100 dark:bg-indigo-900/30',
    },
  ];

  return (
    <div className="space-y-8" data-testid="dashboard">
      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {statCards.map((stat, index) => {
          const Icon = stat.icon;
          return (
            <Card key={index} className="border-border">
              <CardContent className="pt-6">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm text-muted-foreground mb-1">{stat.title}</p>
                    <p className="text-2xl font-bold" style={{ fontFamily: 'JetBrains Mono, monospace' }}>
                      {stat.value}
                    </p>
                  </div>
                  <div className={`p-3 rounded-sm ${stat.bg}`}>
                    <Icon className={stat.color} size={20} />
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Recent Jobs */}
      <Card className="border-border">
        <CardHeader>
          <CardTitle>Jobs Recentes</CardTitle>
        </CardHeader>
        <CardContent>
          {stats?.recent_jobs && stats.recent_jobs.length > 0 ? (
            <div className="space-y-3">
              {stats.recent_jobs.map((job) => (
                <div
                key={job.id}
                onClick={() => navigate(`/results?job=${job.id}`)}
                className="flex items-center justify-between p-4 border border-slate-200 rounded-sm hover:bg-muted/50 transition-colors cursor-pointer"
                data-testid={`job-${job.id}`}
              >
                  <div className="flex-1">
                    <p className="font-medium text-sm">{job.filename}</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      {job.total_items} itens • {job.found_items} encontrados
                    </p>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="text-right">
                      <p className="text-sm font-mono font-bold text-green-700">
                        {job.total_savings ? `€${job.total_savings.toFixed(2)}` : '€0.00'}
                      </p>
                      <p className="text-xs text-muted-foreground">economia</p>
                    </div>
                    <Badge
                      variant={job.status === 'completed' ? 'default' : job.status === 'running' ? 'secondary' : 'outline'}
                      data-testid={`job-status-${job.id}`}
                    >
                      {job.status === 'completed' && 'Completo'}
                      {job.status === 'running' && 'Em execução'}
                      {job.status === 'pending' && 'Pendente'}
                      {job.status === 'failed' && 'Erro'}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-center text-muted-foreground py-8">Nenhum job encontrado</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default Dashboard;
