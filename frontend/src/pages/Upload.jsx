import React, { useState } from 'react';
import { jobsAPI } from '../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Upload as UploadIcon, FileSpreadsheet, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { useNavigate } from 'react-router-dom';

const Upload = () => {
  const navigate = useNavigate();
  const [file, setFile] = useState(null);
  const [thresholdEuro, setThresholdEuro] = useState(5);
  const [thresholdPercent, setThresholdPercent] = useState(10);
  const [uploading, setUploading] = useState(false);
  const [jobId, setJobId] = useState(null);
  const [running, setRunning] = useState(false);

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile) {
      if (!selectedFile.name.endsWith('.xlsx') && !selectedFile.name.endsWith('.xls')) {
        toast.error('Por favor, selecione um ficheiro Excel (.xlsx ou .xls)');
        return;
      }
      setFile(selectedFile);
      toast.success(`Ficheiro selecionado: ${selectedFile.name}`);
    }
  };

  const handleUpload = async () => {
    if (!file) {
      toast.error('Por favor, selecione um ficheiro');
      return;
    }

    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('threshold_euro', thresholdEuro);
      formData.append('threshold_percent', thresholdPercent);

      const { data } = await jobsAPI.upload(formData);
      setJobId(data.id);
      toast.success(`Job criado com ${data.total_items} itens!`);
    } catch (error) {
      console.error('Upload error:', error);
      toast.error(error.response?.data?.detail || 'Erro ao fazer upload');
    } finally {
      setUploading(false);
    }
  };

  const handleRun = async () => {
    if (!jobId) return;

    setRunning(true);
    try {
      await jobsAPI.run(jobId);
      toast.success('Job iniciado! A processar...');
      // Navigate to results page after 2 seconds
      setTimeout(() => {
        navigate('/results');
      }, 2000);
    } catch (error) {
      console.error('Run error:', error);
      toast.error(error.response?.data?.detail || 'Erro ao iniciar job');
      setRunning(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6" data-testid="upload-page">
      <Card className="border-slate-200">
        <CardHeader>
          <CardTitle>Upload Excel</CardTitle>
          <p className="text-sm text-slate-600 mt-2">
            Formato esperado: RefID | Medida | Marca | Modelo | Indice | MeuPreço
          </p>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* File Upload */}
          <div>
            <Label htmlFor="file-upload" className="block mb-2">
              Ficheiro Excel
            </Label>
            <div className="border-2 border-dashed border-slate-300 rounded-sm p-8 text-center hover:border-slate-400 transition-colors">
              <input
                id="file-upload"
                type="file"
                accept=".xlsx,.xls"
                onChange={handleFileChange}
                className="hidden"
                data-testid="file-input"
              />
              <label htmlFor="file-upload" className="cursor-pointer">
                {file ? (
                  <div className="flex items-center justify-center gap-3">
                    <FileSpreadsheet className="text-green-600" size={32} />
                    <div className="text-left">
                      <p className="font-medium text-slate-900">{file.name}</p>
                      <p className="text-sm text-slate-500">{(file.size / 1024).toFixed(2)} KB</p>
                    </div>
                  </div>
                ) : (
                  <div>
                    <UploadIcon className="mx-auto text-slate-400 mb-3" size={40} />
                    <p className="text-sm text-slate-600">
                      Clique para selecionar ou arraste o ficheiro
                    </p>
                    <p className="text-xs text-slate-500 mt-1">Apenas .xlsx ou .xls</p>
                  </div>
                )}
              </label>
            </div>
          </div>

          {/* Thresholds */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label htmlFor="threshold-euro">Threshold € Mínimo</Label>
              <Input
                id="threshold-euro"
                type="number"
                step="0.1"
                value={thresholdEuro}
                onChange={(e) => setThresholdEuro(parseFloat(e.target.value))}
                data-testid="threshold-euro-input"
              />
            </div>
            <div>
              <Label htmlFor="threshold-percent">Threshold % Mínimo</Label>
              <Input
                id="threshold-percent"
                type="number"
                step="0.1"
                value={thresholdPercent}
                onChange={(e) => setThresholdPercent(parseFloat(e.target.value))}
                data-testid="threshold-percent-input"
              />
            </div>
          </div>

          {/* Actions */}
          <div className="space-y-3">
            <Button
              onClick={handleUpload}
              disabled={!file || uploading || jobId}
              className="w-full"
              data-testid="upload-btn"
            >
              {uploading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {jobId ? 'Ficheiro Carregado' : 'Carregar Ficheiro'}
            </Button>

            {jobId && (
              <Button
                onClick={handleRun}
                disabled={running}
                className="w-full bg-green-700 hover:bg-green-800"
                data-testid="run-btn"
              >
                {running && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Iniciar Pesquisa
              </Button>
            )}
          </div>

          {jobId && (
            <div className="p-4 bg-green-50 border border-green-200 rounded-sm">
              <p className="text-sm text-green-800">
                ✓ Job criado com sucesso! ID: <span className="font-mono">{jobId.substring(0, 8)}</span>
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Instructions */}
      <Card className="border-slate-200 bg-slate-50">
        <CardHeader>
          <CardTitle className="text-base">Instruções</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-slate-700 space-y-2">
          <p>1. Prepare o ficheiro Excel com as colunas: RefID, Medida, Marca, Modelo, Indice, MeuPreço</p>
          <p>2. Defina os thresholds de alerta (economia mínima em € ou %)</p>
          <p>3. Carregue o ficheiro e clique em "Iniciar Pesquisa"</p>
          <p>4. Aguarde o processamento e veja os resultados na página "Resultados"</p>
        </CardContent>
      </Card>
    </div>
  );
};

export default Upload;
