import React from 'react';
import { useSearchParams } from 'react-router-dom';
import { PageHeader } from '../components/common';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import Comparar from './Comparar';
import Results from './Results';

const Campanhas = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get('tab') === 'historico' ? 'historico' : 'nova';

  const changeTab = (value) => {
    setSearchParams(value === 'historico' ? { tab: 'historico' } : {}, { replace: true });
  };

  const openSaved = (jobId) => {
    setSearchParams({ tab: 'historico', job: jobId });
  };

  return (
    <div className="space-y-5" data-testid="campanhas-page">
      <PageHeader
        eyebrow="Campanhas de fornecedores"
        title="Campanhas"
        description="Carregue a lista da campanha do fornecedor, compare com o seu preço e consulte as campanhas guardadas."
      />
      <Tabs value={tab} onValueChange={changeTab}>
        <TabsList>
          <TabsTrigger value="nova" data-testid="tab-nova-campanha">Nova campanha</TabsTrigger>
          <TabsTrigger value="historico" data-testid="tab-historico">Histórico</TabsTrigger>
        </TabsList>
        {/* Sempre montado: uma comparação em curso não se perde ao mudar de separador. */}
        <TabsContent value="nova" forceMount className="mt-5 data-[state=inactive]:hidden">
          <Comparar embedded onSaved={openSaved} />
        </TabsContent>
        <TabsContent value="historico" className="mt-5">
          <Results embedded />
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default Campanhas;
