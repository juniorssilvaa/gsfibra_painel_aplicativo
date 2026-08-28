import React, { useEffect, useState } from 'react';
import { toast } from '../lib/notify';
import axios from 'axios';
import { Image as ImageIcon, Trash2, Upload } from 'lucide-react';

export default function GaleriaPage({ provedorId }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [nome, setNome] = useState('');
  const [file, setFile] = useState(null);

  const loadItems = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const params = {};
      if (provedorId) {
        params.provedor = provedorId;
      }
      const res = await axios.get('/api/provider-gallery/', {
        headers: { Authorization: `Token ${token}` },
        params,
      });
      const data = res.data?.results || res.data || [];
      setItems(data);
    } catch (err) {
      setItems([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (provedorId) loadItems();
  }, [provedorId]);

  const handleUpload = async () => {
    if (!file || !nome.trim()) {
      toast.error('Informe nome e selecione uma imagem.');
      return;
    }
    setSending(true);
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const formData = new FormData();
      formData.append('nome', nome.trim());
      formData.append('imagem', file);
      if (provedorId) {
        formData.append('provedor', provedorId);
      }
      const created = await axios.post('/api/provider-gallery/', formData, {
        headers: {
          Authorization: `Token ${token}`,
          'Content-Type': 'multipart/form-data',
        },
      });
      setNome('');
      setFile(null);
      if (created?.data?.id) {
        setItems((prev) => [created.data, ...prev.filter((i) => i.id !== created.data.id)]);
      }
      await loadItems();
    } catch (err) {
      toast.apiError(err, 'Erro ao enviar imagem.');
    } finally {
      setSending(false);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Remover esta imagem da galeria?')) return;
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      await axios.delete(`/api/provider-gallery/${id}/`, {
        headers: { Authorization: `Token ${token}` },
        params: provedorId ? { provedor: provedorId } : {},
      });
      await loadItems();
      toast.deleted('Imagem removida da galeria.');
    } catch (err) {
      await loadItems();
      toast.apiError(err, 'Erro ao remover imagem.');
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-black text-foreground tracking-tight">Galeria</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Use variáveis no nome, ex.: <span className="font-mono text-foreground/80">{'{planos}'}</span>.
          A IA alterna imagem e texto da aba Planos; na base de conhecimento você pode
          pedir &quot;somente imagem&quot; para planos.
        </p>
      </div>

      <div className="bg-card border border-border rounded-2xl p-4 md:p-6 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <input
            type="text"
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            placeholder={'Nome (ex: Cartão 500MB {planos})'}
            className="niochat-input md:col-span-2"
          />
          <input
            type="file"
            accept="image/*"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="niochat-input"
          />
        </div>
        <button
          onClick={handleUpload}
          disabled={sending}
          className="inline-flex items-center gap-2 px-6 py-2 rounded-[4px] bg-[#0070BA] text-white hover:bg-[#005fa3] disabled:opacity-60 transition-colors font-medium text-sm shadow-sm"
        >
          <Upload size={16} />
          {sending ? 'Enviando...' : 'Enviar imagem'}
        </button>
      </div>

      {loading ? (
        <div className="text-muted-foreground">Carregando galeria...</div>
      ) : items.length === 0 ? (
        <div className="bg-card border border-border rounded-2xl p-8 text-center text-muted-foreground">
          Nenhuma imagem cadastrada.
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {items.map((item) => (
            <div key={item.id} className="bg-card border border-border rounded-xl overflow-hidden">
              <div className="aspect-video bg-muted/30 flex items-center justify-center overflow-hidden">
                {item.image_url ? (
                  <img src={item.image_url} alt={item.nome} className="w-full h-full object-cover" />
                ) : (
                  <ImageIcon className="w-8 h-8 text-muted-foreground" />
                )}
              </div>
              <div className="p-3 flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-semibold text-sm truncate">{item.nome}</p>
                </div>
                <button
                  onClick={() => handleDelete(item.id)}
                  className="p-2 rounded-lg text-red-500 hover:bg-red-500/10"
                  title="Remover"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
