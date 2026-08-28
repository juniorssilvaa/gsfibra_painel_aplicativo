import React, { useState, useEffect } from 'react';
import { Palette } from 'lucide-react';
import { useParams } from 'react-router-dom';
import AppPreview from './AppPreview';
import axios from 'axios';

export default function AppearancePage() {
  const { provedorId } = useParams();
  const [providerName, setProviderName] = useState('PROVEDOR');
  const [settings, setSettings] = useState({
    appearance: {
      theme: 'dark',
      language: 'pt-BR',
      timezone: 'America/Sao_Paulo'
    }
  });

  useEffect(() => {
    if (provedorId) {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      if (token) {
        axios.get(`/api/provedores/${provedorId}/`, {
          headers: { Authorization: `Token ${token}` }
        })
          .then(res => {
            if (res.data?.nome) setProviderName(res.data.nome);
          })
          .catch(err => console.error('Error fetching provider info:', err));
      }
    }
  }, [provedorId]);

  return (
    <div className="flex-1 p-6 bg-background overflow-y-auto">
      <div className="max-w-6xl mx-auto">
        <h1 className="text-3xl font-bold text-foreground mb-8 flex items-center gap-3">
          <Palette className="w-8 h-8 text-white/70" /> Aparência
        </h1>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-start">
          {/* Settings Column */}
          <div className="space-y-6">
            <div className="niochat-card p-6 border border-border shadow-sm">
              <h3 className="text-lg font-medium text-white mb-6">
                Aparência e Localização
              </h3>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-white mb-2">
                    Tema do Painel e App
                  </label>
                  <div className="grid grid-cols-3 gap-3">
                    {['dark', 'light', 'auto'].map((t) => (
                      <button
                        key={t}
                        onClick={() => setSettings({
                          ...settings,
                          appearance: { ...settings.appearance, theme: t }
                        })}
                        className={`py-2 px-4 rounded-lg border text-sm font-medium transition-all ${settings.appearance.theme === t
                            ? 'bg-primary text-primary-foreground border-primary shadow-md'
                            : 'bg-background text-white/70 border-border hover:border-primary/50'
                          }`}
                      >
                        {t === 'dark' ? 'Escuro' : t === 'light' ? 'Claro' : 'Auto'}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="pt-4 border-t border-border">
                  <label className="block text-sm font-medium text-white mb-2">
                    Idioma Principal
                  </label>
                  <select
                    value={settings.appearance.language}
                    onChange={(e) => setSettings({
                      ...settings,
                      appearance: { ...settings.appearance, language: e.target.value }
                    })}
                    className="niochat-input w-full"
                  >
                    <option value="pt-BR">Português (Brasil)</option>
                    <option value="en-US">English (US)</option>
                    <option value="es-ES">Español</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-white mb-2">
                    Fuso Horário
                  </label>
                  <select
                    value={settings.appearance.timezone}
                    onChange={(e) => setSettings({
                      ...settings,
                      appearance: { ...settings.appearance, timezone: e.target.value }
                    })}
                    className="niochat-input w-full"
                  >
                    <option value="America/Sao_Paulo">São Paulo (GMT-3)</option>
                    <option value="America/New_York">New York (GMT-5)</option>
                    <option value="Europe/London">London (GMT+0)</option>
                  </select>
                </div>
              </div>
            </div>

            <div className="p-4 bg-muted/30 rounded-lg border border-border text-sm text-white/70">
              <p>
                As alterações de tema são refletidas instantaneamente na interface de pré-visualização ao lado.
              </p>
            </div>
          </div>

          {/* Preview Column */}
          <div className="sticky top-0 bg-muted/20 rounded-3xl p-8 border border-border/50 backdrop-blur-sm">
            <AppPreview
              theme={settings.appearance.theme === 'auto' ? 'dark' : settings.appearance.theme}
              providerName={providerName}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
