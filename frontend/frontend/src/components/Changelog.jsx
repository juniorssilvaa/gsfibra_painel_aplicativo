import React, { useState, useEffect, useMemo } from 'react';
import { X, Calendar, Package } from 'lucide-react';

const Changelog = ({ isOpen, onClose }) => {
  const [versions, setVersions] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadChangelog = async () => {
      try {
        setLoading(true);
        const response = await fetch('/api/changelog/');
        if (response.ok) {
          const data = await response.json();
          const versionsData = Array.isArray(data) ? data : (data?.versions || []);
          setVersions(versionsData);
        }
      } catch (error) {
        console.error('Erro ao carregar changelog:', error);
      } finally {
        setLoading(false);
      }
    };

    if (isOpen) {
      loadChangelog();
    }
  }, [isOpen]);

  // Agrupa mudanças por módulo para uma versão específica
  const groupByModule = (changes) => {
    if (!Array.isArray(changes)) return {};
    return changes.reduce((acc, change) => {
      const module = change.module || 'Geral';
      if (!acc[module]) acc[module] = [];
      acc[module].push(change);
      return acc;
    }, {});
  };

  const getBadgeStyles = (type) => {
    switch (type) {
      case 'feature':
        return 'bg-blue-600 text-white'; // Novo (Azul)
      case 'improvement':
        return 'bg-teal-500 text-white'; // Atualização (Teal/Ciano)
      case 'fix':
        return 'bg-yellow-500 text-black'; // Correção (Amarelo)
      default:
        return 'bg-gray-600 text-white';
    }
  };

  const getBadgeLabel = (type) => {
    switch (type) {
      case 'feature': return 'Novo';
      case 'improvement': return 'Atualização';
      case 'fix': return 'Correção';
      default: return 'Outro';
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return '';
    const parts = dateString.split('-');
    if (parts.length === 3) {
      return `${parts[2]}/${parts[1]}/${parts[0]}`;
    }
    return dateString;
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-md z-50 flex items-center justify-center p-4">
      <div className="bg-background rounded-xl border border-border w-full max-w-5xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden">

        {/* Header Fixo */}
        <div className="flex items-center justify-between p-5 border-b border-border bg-card">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-primary/10 rounded-lg">
              <Package className="w-5 h-5 text-primary" />
            </div>
            <h2 className="text-lg font-semibold text-foreground uppercase tracking-wider">Histórico de Versões</h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-muted rounded-full transition-colors group"
          >
            <X className="w-5 h-5 text-muted-foreground group-hover:text-foreground" />
          </button>
        </div>

        {/* Scrolling Content */}
        <div className="flex-1 overflow-y-auto p-0 scrollbar-thin scrollbar-thumb-muted-foreground/20">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-24 gap-4">
              <div className="animate-spin rounded-full h-10 w-10 border-t-2 border-b-2 border-primary"></div>
              <p className="text-muted-foreground font-light tracking-wide">Sincronizando melhorias...</p>
            </div>
          ) : (
            <div className="divide-y divide-border">
              {versions.map((v) => (
                <div key={v.version} className="p-8 last:border-b-0 space-y-8 bg-card/30">

                  {/* Versão Header (Estilo Imagem Referência) */}
                  <div className="flex items-center justify-between border-b border-border pb-3">
                    <h3 className="text-xl font-bold text-foreground">
                      Versão: {v.version}
                    </h3>
                    <div className="flex items-center gap-2 text-muted-foreground font-medium bg-muted px-3 py-1 rounded-full text-sm border border-border">
                      <Calendar className="w-4 h-4" />
                      <span>{formatDate(v.date)}</span>
                    </div>
                  </div>

                  {/* Grupos por Módulo */}
                  <div className="space-y-10">
                    {Object.entries(groupByModule(v.changes)).map(([module, changes]) => (
                      <div key={module} className="space-y-4">
                        <h4 className="text-muted-foreground font-bold text-xs uppercase tracking-widest flex items-center gap-2">
                          <span className="w-1.5 h-1.5 rounded-full bg-primary shadow-[0_0_8px_rgba(59,130,246,0.8)]"></span>
                          {module}
                        </h4>

                        <div className="space-y-5 pl-4 border-l border-border ml-0.5">
                          {changes.map((change, idx) => (
                            <div key={idx} className="group relative">
                              <div className="flex items-start gap-4">
                                <span className={`shrink-0 px-2 py-0.5 mt-0.5 rounded text-[10px] uppercase font-bold tracking-tighter shadow-sm ${getBadgeStyles(change.type)}`}>
                                  {getBadgeLabel(change.type)}
                                </span>

                                <div className="flex-1">
                                  <div className="text-[15px] leading-relaxed text-foreground/90 group-hover:text-foreground transition-colors">
                                    <span className="font-medium">{change.title}</span>
                                    {change.description && (
                                      <span className="text-muted-foreground text-sm ml-2 font-normal italic">
                                        — {change.description}
                                      </span>
                                    )}
                                  </div>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Changelog;