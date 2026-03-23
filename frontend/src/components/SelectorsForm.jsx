import React, { useState, useEffect } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from './ui/dialog';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Textarea } from './ui/textarea';
import { Loader2, Code, Save } from 'lucide-react';
import { suppliersAPI } from '../lib/api';
import { toast } from 'sonner';

const SelectorsForm = ({ open, onClose, supplier }) => {
  const [selectors, setSelectors] = useState({
    login_username: '',
    login_password: '',
    login_button: '',
    search_input: '',
    search_button: '',
    price_pattern: '',
    notes: ''
  });
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open && supplier) {
      loadSelectors();
    }
  }, [open, supplier]);

  const loadSelectors = async () => {
    setLoading(true);
    try {
      const { data } = await suppliersAPI.getSelectors(supplier.id);
      setSelectors(data);
    } catch (error) {
      console.error('Error loading selectors:', error);
      toast.error('Erro ao carregar seletores');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await suppliersAPI.updateSelectors(supplier.id, selectors);
      toast.success('Seletores atualizados com sucesso!');
      onClose();
    } catch (error) {
      console.error('Error saving selectors:', error);
      toast.error('Erro ao guardar seletores');
    } finally {
      setSaving(false);
    }
  };

  const handleChange = (field, value) => {
    setSelectors(prev => ({ ...prev, [field]: value }));
  };

  if (!supplier) return null;

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="selectors-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Code className="w-5 h-5" />
            Seletores CSS - {supplier.name}
          </DialogTitle>
          <DialogDescription>
            Configure os seletores CSS usados pelo scraper para fazer login e pesquisar neste fornecedor.
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
          </div>
        ) : (
          <div className="space-y-4 py-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="login_username">Seletor Username</Label>
                <Input
                  id="login_username"
                  value={selectors.login_username}
                  onChange={(e) => handleChange('login_username', e.target.value)}
                  placeholder="Ex: #username, input[name='user']"
                  className="font-mono text-sm"
                  data-testid="selector-login-username"
                />
                <p className="text-xs text-slate-500 mt-1">Seletor CSS do campo de username</p>
              </div>

              <div>
                <Label htmlFor="login_password">Seletor Password</Label>
                <Input
                  id="login_password"
                  value={selectors.login_password}
                  onChange={(e) => handleChange('login_password', e.target.value)}
                  placeholder="Ex: #password, input[type='password']"
                  className="font-mono text-sm"
                  data-testid="selector-login-password"
                />
                <p className="text-xs text-slate-500 mt-1">Seletor CSS do campo de password</p>
              </div>
            </div>

            <div>
              <Label htmlFor="login_button">Seletor Botão Login</Label>
              <Input
                id="login_button"
                value={selectors.login_button}
                onChange={(e) => handleChange('login_button', e.target.value)}
                placeholder="Ex: button[type='submit'], #loginBtn"
                className="font-mono text-sm"
                data-testid="selector-login-button"
              />
              <p className="text-xs text-slate-500 mt-1">Seletor CSS do botão de login</p>
            </div>

            <div className="border-t pt-4 mt-4">
              <h4 className="font-medium text-sm mb-3">Pesquisa de Produtos</h4>
              
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="search_input">Seletor Campo Pesquisa</Label>
                  <Input
                    id="search_input"
                    value={selectors.search_input}
                    onChange={(e) => handleChange('search_input', e.target.value)}
                    placeholder="Ex: #searchBox, input[name='query']"
                    className="font-mono text-sm"
                    data-testid="selector-search-input"
                  />
                  <p className="text-xs text-slate-500 mt-1">Seletor CSS do campo de pesquisa</p>
                </div>

                <div>
                  <Label htmlFor="search_button">Seletor Botão Pesquisa</Label>
                  <Input
                    id="search_button"
                    value={selectors.search_button}
                    onChange={(e) => handleChange('search_button', e.target.value)}
                    placeholder="Ex: button.search, #searchBtn"
                    className="font-mono text-sm"
                    data-testid="selector-search-button"
                  />
                  <p className="text-xs text-slate-500 mt-1">Seletor CSS do botão de pesquisa</p>
                </div>
              </div>
            </div>

            <div className="border-t pt-4 mt-4">
              <Label htmlFor="price_pattern">Padrão de Preço (Regex)</Label>
              <Input
                id="price_pattern"
                value={selectors.price_pattern}
                onChange={(e) => handleChange('price_pattern', e.target.value)}
                placeholder="Ex: €\\s*(\\d+[,.]\\d{2})"
                className="font-mono text-sm"
                data-testid="selector-price-pattern"
              />
              <p className="text-xs text-slate-500 mt-1">Expressão regular para extrair preços do HTML</p>
            </div>

            <div className="border-t pt-4 mt-4">
              <Label htmlFor="notes">Notas</Label>
              <Textarea
                id="notes"
                value={selectors.notes}
                onChange={(e) => handleChange('notes', e.target.value)}
                placeholder="Notas sobre o processo de scraping deste fornecedor..."
                className="min-h-[80px]"
                data-testid="selector-notes"
              />
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={saving}>
            Cancelar
          </Button>
          <Button onClick={handleSave} disabled={loading || saving} data-testid="save-selectors-btn">
            {saving ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                A guardar...
              </>
            ) : (
              <>
                <Save className="w-4 h-4 mr-2" />
                Guardar Seletores
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default SelectorsForm;
