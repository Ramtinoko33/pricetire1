import React, { useState } from 'react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from './ui/dialog';
import { Loader2 } from 'lucide-react';

const SupplierForm = ({ open, onClose, onSubmit, initialData = null, isLoading = false }) => {
  const [formData, setFormData] = useState(initialData || {
    name: '',
    url_login: '',
    url_search: '',
    username: '',
    password: '',
  });

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    onSubmit(formData);
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[500px]" data-testid="supplier-form-dialog">
        <DialogHeader>
          <DialogTitle>{initialData ? 'Editar Fornecedor' : 'Adicionar Fornecedor'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label htmlFor="name">Nome *</Label>
            <Input
              id="name"
              name="name"
              value={formData.name}
              onChange={handleChange}
              required
              data-testid="supplier-name-input"
            />
          </div>
          <div>
            <Label htmlFor="url_login">URL Login *</Label>
            <Input
              id="url_login"
              name="url_login"
              type="url"
              value={formData.url_login}
              onChange={handleChange}
              required
              data-testid="supplier-url-login-input"
            />
          </div>
          <div>
            <Label htmlFor="url_search">URL Pesquisa *</Label>
            <Input
              id="url_search"
              name="url_search"
              type="url"
              value={formData.url_search}
              onChange={handleChange}
              required
              data-testid="supplier-url-search-input"
            />
          </div>
          <div>
            <Label htmlFor="username">Username *</Label>
            <Input
              id="username"
              name="username"
              value={formData.username}
              onChange={handleChange}
              required
              data-testid="supplier-username-input"
            />
          </div>
          <div>
            <Label htmlFor="password">Password *</Label>
            <Input
              id="password"
              name="password"
              type="password"
              value={formData.password}
              onChange={handleChange}
              required={!initialData}
              placeholder={initialData ? 'Deixar vazio para manter' : ''}
              data-testid="supplier-password-input"
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={isLoading}>
              Cancelar
            </Button>
            <Button type="submit" disabled={isLoading} data-testid="supplier-submit-btn">
              {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {initialData ? 'Atualizar' : 'Adicionar'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default SupplierForm;
