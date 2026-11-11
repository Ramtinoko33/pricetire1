import React, { useCallback, useEffect, useState } from 'react';
import { Check, Loader2, Undo2, X } from 'lucide-react';
import { toast } from 'sonner';
import { brandsAPI } from '@/lib/api';
import { errorMessage, formatDateTime } from '@/lib/format';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { EmptyState, ErrorState, TableSkeleton } from '@/components/common';
import { ToneBadge } from '@/components/badges';

// Marcas mal escritas pelos fornecedores (MICHELIM, MICHELINTBR…): validar a associação à marca
// principal. Validada, as ofertas passam para a marca principal e as recolhas seguintes também.
const MarcasAssociacoes = ({ onChanged }) => {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [choice, setChoice] = useState({});

  const load = useCallback(async () => {
    try {
      const { data: d } = await brandsAPI.aliases();
      setData(d);
      setError('');
    } catch (err) {
      setData({ suggestions: [], decided: [], main_brands: [] });
      setError(errorMessage(err, 'Erro ao carregar as associações'));
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const decide = async (s, status) => {
    const brand = choice[s.alias] ?? s.brand;
    setBusy(s.alias);
    try {
      const { data: r } = await brandsAPI.decideAlias(s.alias, brand, status);
      toast.success(status === 'approved'
        ? `${s.alias} associada a ${brand} (${r.offers_moved} ofertas)`
        : `${s.alias} fica como marca própria`);
      await load();
      onChanged?.();
    } catch (err) {
      toast.error(errorMessage(err, 'Erro ao gravar'));
    } finally {
      setBusy('');
    }
  };

  const undo = async (d) => {
    setBusy(d.alias);
    try {
      await brandsAPI.undoAlias(d.alias);
      toast.success(`${d.alias}: decisão desfeita`);
      await load();
      onChanged?.();
    } catch (err) {
      toast.error(errorMessage(err, 'Erro ao desfazer'));
    } finally {
      setBusy('');
    }
  };

  if (data === null) return <Card><CardContent className="p-0"><TableSkeleton rows={5} cols={5} /></CardContent></Card>;

  return (
    <div className="space-y-4" data-testid="marcas-associacoes">
      {error && <ErrorState message={error} onRetry={load} />}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Por validar</CardTitle>
          <p className="text-xs text-muted-foreground">
            Marcas sem classificação que parecem erros de escrita ou variantes de uma marca principal. Ao associar,
            as ofertas passam para a marca principal e as recolhas seguintes também. Se for uma marca diferente, escolha "Não é".
          </p>
        </CardHeader>
        <CardContent className="p-0">
          {data.suggestions.length === 0 ? (
            <EmptyState title="Nada por validar" description="Não há marcas suspeitas de erro de escrita." />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Marca do fornecedor</TableHead>
                  <TableHead>Marca principal</TableHead>
                  <TableHead className="hidden md:table-cell">Motivo</TableHead>
                  <TableHead className="text-right">Ofertas</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.suggestions.map((s) => (
                  <TableRow key={s.alias} data-testid="alias-suggestion">
                    <TableCell className="font-medium">{s.alias}</TableCell>
                    <TableCell>
                      <select
                        value={choice[s.alias] ?? s.brand}
                        onChange={(e) => setChoice((c) => ({ ...c, [s.alias]: e.target.value }))}
                        aria-label={`Marca principal de ${s.alias}`}
                        className="h-8 w-44 rounded-md border bg-background px-2 text-xs"
                      >
                        {data.main_brands.map((b) => <option key={b} value={b}>{b}</option>)}
                      </select>
                    </TableCell>
                    <TableCell className="hidden md:table-cell text-xs text-muted-foreground">{s.reason}</TableCell>
                    <TableCell className="text-right font-mono text-xs">{s.offers}</TableCell>
                    <TableCell className="text-right whitespace-nowrap">
                      {busy === s.alias ? <Loader2 size={14} className="inline animate-spin" /> : (
                        <div className="flex justify-end gap-1.5">
                          <Button size="sm" onClick={() => decide(s, 'approved')} data-testid="alias-approve">
                            <Check size={14} className="mr-1" /> Associar
                          </Button>
                          <Button size="sm" variant="outline" onClick={() => decide(s, 'rejected')} data-testid="alias-reject">
                            <X size={14} className="mr-1" /> Não é
                          </Button>
                        </div>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {data.decided.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-base">Decididas</CardTitle></CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Marca do fornecedor</TableHead>
                  <TableHead>Decisão</TableHead>
                  <TableHead className="hidden md:table-cell">Por</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.decided.map((d) => (
                  <TableRow key={d.alias} data-testid="alias-decided">
                    <TableCell className="font-medium">{d.alias}</TableCell>
                    <TableCell>
                      {d.status === 'approved'
                        ? <ToneBadge tone="green">Associada a {d.brand}</ToneBadge>
                        : <ToneBadge>Marca própria</ToneBadge>}
                    </TableCell>
                    <TableCell className="hidden md:table-cell text-xs text-muted-foreground whitespace-nowrap">
                      {d.decided_at ? formatDateTime(d.decided_at) : '—'} {d.decided_by ? `· ${d.decided_by}` : ''}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button size="sm" variant="ghost" onClick={() => undo(d)} disabled={busy === d.alias}>
                        <Undo2 size={14} className="mr-1" /> Desfazer
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default MarcasAssociacoes;
