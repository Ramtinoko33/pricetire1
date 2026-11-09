import React from 'react';
import { ExternalLink } from 'lucide-react';
import { toast } from 'sonner';
import { compactSize, opensResults, slashedSize, supplierSearchUrl } from '@/lib/supplierLinks';

// Abre o portal do fornecedor. Quando o portal não aceita a medida no endereço,
// copia-a para a área de transferência para colar no campo de pesquisa.
export default function SupplierLink({ offer, className = '' }) {
  const url = supplierSearchUrl(offer.supplier_name, offer.size_key);
  if (!url) return <span className={`whitespace-nowrap ${className}`}>{offer.supplier_name || '—'}</span>;
  const direct = opensResults(offer.supplier_name);
  const medida = /cruzeiro/i.test(offer.supplier_name || '') ? slashedSize(offer.size_key) : compactSize(offer.size_key);
  const onClick = () => {
    if (direct || !medida) return;
    try {
      navigator.clipboard?.writeText(medida);
      toast.success(`Medida ${medida} copiada`, { description: `Cole-a na pesquisa do ${offer.supplier_name}.` });
    } catch {
      /* sem acesso à área de transferência */
    }
  };
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      onClick={onClick}
      className={`inline-flex items-center gap-1 hover:underline whitespace-nowrap ${className}`}
      title={direct ? 'Abrir os resultados desta medida no portal do fornecedor' : `Abrir o portal do fornecedor (a medida ${medida} é copiada para colar na pesquisa)`}
    >
      {offer.supplier_name} <ExternalLink size={12} />
    </a>
  );
}
