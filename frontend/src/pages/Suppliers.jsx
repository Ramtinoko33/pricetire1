import React, { useEffect, useState } from 'react';
import { suppliersAPI } from '../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';
import { Plus, Trash2, TestTube, Power, Loader2, Code } from 'lucide-react';
import { toast } from 'sonner';
import SupplierForm from '../components/SupplierForm';
import SelectorsForm from '../components/SelectorsForm';

const Suppliers = () => {
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [formOpen, setFormOpen] = useState(false);
  const [formLoading, setFormLoading] = useState(false);
  const [testingId, setTestingId] = useState(null);
  const [selectorsOpen, setSelectorsOpen] = useState(false);
  const [selectedSupplier, setSelectedSupplier] = useState(null);

  useEffect(() => {
    loadSuppliers();
  }, []);

  const loadSuppliers = async () => {
    try {
      const { data } = await suppliersAPI.getAll();
      setSuppliers(data);
    } catch (error) {
      console.error('Error loading suppliers:', error);
      toast.error('Erro ao carregar fornecedores');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (formData) => {
    setFormLoading(true);
    try {
      await suppliersAPI.create(formData);
      toast.success('Fornecedor adicionado com sucesso!');
      setFormOpen(false);
      loadSuppliers();
    } catch (error) {
      console.error('Error creating supplier:', error);
      toast.error(error.response?.data?.detail || 'Erro ao adicionar fornecedor');
    } finally {
      setFormLoading(false);
    }
  };

  const handleDelete = async (id, name) => {
    if (!window.confirm(`Tem certeza que deseja eliminar ${name}?`)) return;

    try {
      await suppliersAPI.delete(id);
      toast.success('Fornecedor eliminado');
      loadSuppliers();
    } catch (error) {
      console.error('Error deleting supplier:', error);
      toast.error('Erro ao eliminar fornecedor');
    }
  };

  const handleTestLogin = async (id, name) => {
    setTestingId(id);
    try {
      const { data } = await suppliersAPI.testLogin(id);
      if (data.success) {
        toast.success(`Login OK: ${name}`);
      } else {
        toast.error(`Login falhou: ${data.message}`);
      }
      loadSuppliers();
    } catch (error) {
      console.error('Error testing login:', error);
      toast.error('Erro ao testar login');
    } finally {
      setTestingId(null);
    }
  };

  const handleToggleActive = async (id, currentStatus) => {
    try {
      await suppliersAPI.update(id, { is_active: !currentStatus });
      toast.success(currentStatus ? 'Fornecedor desativado' : 'Fornecedor ativado');
      loadSuppliers();
    } catch (error) {
      console.error('Error toggling supplier:', error);
      toast.error('Erro ao atualizar fornecedor');
    }
  };

  const handleOpenSelectors = (supplier) => {
    setSelectedSupplier(supplier);
    setSelectorsOpen(true);
  };

  if (loading) {
    return <div className="text-center py-12" data-testid="loading">A carregar...</div>;
  }

  return (
    <div className="space-y-6" data-testid="suppliers-page">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold" style={{ fontFamily: 'Chivo, sans-serif' }}>Fornecedores</h2>
          <p className="text-sm text-slate-600 mt-1">{suppliers.length} fornecedores cadastrados</p>
        </div>
        <Button onClick={() => setFormOpen(true)} data-testid="add-supplier-btn">
          <Plus size={18} className="mr-2" />
          Adicionar Fornecedor
        </Button>
      </div>

      <Card className="border-slate-200">
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nome</TableHead>
                <TableHead>URL Login</TableHead>
                <TableHead>Username</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Último Teste</TableHead>
                <TableHead className="text-right">Ações</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {suppliers.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center py-8 text-slate-500">
                    Nenhum fornecedor cadastrado
                  </TableCell>
                </TableRow>
              ) : (
                suppliers.map((supplier) => (
                  <TableRow key={supplier.id} data-testid={`supplier-row-${supplier.id}`}>
                    <TableCell className="font-medium">{supplier.name}</TableCell>
                    <TableCell className="text-sm text-slate-600 max-w-xs truncate">{supplier.url_login}</TableCell>
                    <TableCell className="text-sm font-mono">{supplier.username}</TableCell>
                    <TableCell>
                      <Badge variant={supplier.is_active ? 'default' : 'secondary'}>
                        {supplier.is_active ? 'Ativo' : 'Inativo'}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-sm text-slate-600">
                      {supplier.last_test
                        ? new Date(supplier.last_test).toLocaleDateString('pt-PT')
                        : 'Nunca'}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center justify-end gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleOpenSelectors(supplier)}
                          title="Configurar Seletores CSS"
                          data-testid={`selectors-btn-${supplier.id}`}
                        >
                          <Code size={14} />
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleTestLogin(supplier.id, supplier.name)}
                          disabled={testingId === supplier.id}
                          data-testid={`test-login-btn-${supplier.id}`}
                        >
                          {testingId === supplier.id ? (
                            <Loader2 size={14} className="animate-spin" />
                          ) : (
                            <TestTube size={14} />
                          )}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleToggleActive(supplier.id, supplier.is_active)}
                          data-testid={`toggle-active-btn-${supplier.id}`}
                        >
                          <Power size={14} className={supplier.is_active ? 'text-green-600' : 'text-slate-400'} />
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleDelete(supplier.id, supplier.name)}
                          data-testid={`delete-btn-${supplier.id}`}
                        >
                          <Trash2 size={14} className="text-red-600" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <SupplierForm
        open={formOpen}
        onClose={() => setFormOpen(false)}
        onSubmit={handleCreate}
        isLoading={formLoading}
      />

      <SelectorsForm
        open={selectorsOpen}
        onClose={() => setSelectorsOpen(false)}
        supplier={selectedSupplier}
      />
    </div>
  );
};

export default Suppliers;
