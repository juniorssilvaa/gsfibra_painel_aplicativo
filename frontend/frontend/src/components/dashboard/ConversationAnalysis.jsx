import React, { useState, useEffect } from 'react';
import { Card, CardContent } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, PieChart, Pie, Cell, Tooltip } from 'recharts';
import axios from 'axios';
import { buildApiPath } from '@/utils/apiBaseUrl';

const CHANNEL_LABELS = {
  whatsapp: 'WhatsApp',
  whatsapp_session: 'WhatsApp QR',
  whatsapp_oficial: 'WhatsApp Oficial',
  telegram: 'Telegram',
  email: 'Email',
  webchat: 'Chat Web',
  instagram: 'Instagram',
  facebook: 'Facebook'
};

const prettifyChannelName = (name) => {
  if (!name) return 'Canal';
  const normalized = String(name).toLowerCase().trim();
  if (CHANNEL_LABELS[normalized]) return CHANNEL_LABELS[normalized];
  if (normalized.includes('whatsapp') && normalized.includes('oficial')) return 'WhatsApp Oficial';
  if (normalized.includes('whatsapp') && normalized.includes('session')) return 'WhatsApp QR';
  return String(name).replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
};

export default function ConversationAnalysis({ provedorId }) {
  const [selectedPeriod, setSelectedPeriod] = useState('week');
  const [analysisData, setAnalysisData] = useState(null);
  const [loading, setLoading] = useState(false);

  // Períodos disponíveis
  const periods = {
    today: { label: 'Últimas 24 horas' },
    week: { label: 'Últimos 7 dias' },
    month: { label: 'Últimos 30 dias' },
    quarter: { label: 'Últimos 3 meses' }
  };

  // Buscar dados da API
  const fetchAnalysisData = async (period) => {
    try {
      setLoading(true);
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      
      if (!token) {
        throw new Error('Token não encontrado. Faça login novamente.');
      }
      
      const query = provedorId ? `?period=${period}&provedor_id=${provedorId}` : `?period=${period}`;
      const response = await axios.get(buildApiPath(`/api/analysis/${query}`), {
        headers: {
          'Authorization': `Token ${token}`
        }
      });
      
      if (response.status === 200) {
        const apiData = response.data;
        console.log('Dados da API completos:', apiData);
        console.log('Summary:', apiData.summary);
        console.log('Channel Distribution:', apiData.channelDistribution);
        console.log('Conversations by Day:', apiData.conversationsByDay);
        
        // Transformar dados da API para o formato esperado pelo frontend
        const transformedData = {
          totalConversations: apiData.summary?.totalConversations || 0,
          channels: apiData.channelDistribution?.map(channel => ({
            name: prettifyChannelName(channel.name),
            count: channel.value,
            percentage: `${Math.round((channel.value / (apiData.summary?.totalConversations || 1)) * 100)}%`,
            color: channel.color
          })) || [],
          dailyVolume: apiData.conversationsByDay?.map(day => ({
            date: day.date,
            volume: day.conversations
          })) || []
        };
        
        setAnalysisData(transformedData);
      } else {
        console.error('Erro ao buscar análise:', response.status);
        // Dados vazios em caso de erro
        setAnalysisData({
          totalConversations: 0,
          channels: [],
          dailyVolume: []
        });
      }
    } catch (error) {
      console.error('Erro ao buscar dados de análise:', error);
      // Dados vazios em caso de erro
      setAnalysisData({
        totalConversations: 0,
        channels: [],
        dailyVolume: []
      });
    } finally {
      setLoading(false);
    }
  };



  useEffect(() => {
    fetchAnalysisData(selectedPeriod);
  }, [selectedPeriod, provedorId]);

  const data = analysisData || {
    totalConversations: 0,
    channels: [],
    dailyVolume: []
  };

  return (
    <Card className="bg-card border-border">
      <CardContent className="p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6 pb-4 border-b border-border/60">
          <h2 className="text-xl font-semibold text-foreground">Análise de Conversas</h2>
          <div className="flex items-center gap-4">
            <span className="text-muted-foreground text-sm">Total de Conversas</span>
            <span className="text-3xl font-bold text-foreground">{data.totalConversations}</span>
          </div>
        </div>

        {/* Período Selecionado */}
        <div className="mb-6">
          <label className="block text-muted-foreground text-sm mb-2">Período Selecionado</label>
          <Select value={selectedPeriod} onValueChange={setSelectedPeriod}>
            <SelectTrigger className="w-48 bg-background border-border text-foreground">
              <SelectValue />
            </SelectTrigger>
            <SelectContent className="bg-popover border-border">
              {Object.entries(periods).map(([key, period]) => (
                <SelectItem key={key} value={key} className="text-foreground hover:bg-accent">
                  {period.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-green-400"></div>
          </div>
        ) : data.totalConversations === 0 && data.channels.length === 0 ? (
          <div className="flex items-center justify-center h-64">
            <div className="text-center">
              <div className="text-4xl text-gray-400 mb-2"></div>
              <p className="text-gray-400">Nenhum dado disponível</p>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Conversas por Canal */}
            <div>
              <h3 className="text-lg font-medium text-foreground mb-4">Conversas por Canal</h3>
              
              {data.channels.length === 0 ? (
                <div className="flex items-center justify-center h-32">
                  <div className="text-center">
                    <div className="text-2xl text-gray-400 mb-1">-</div>
                    <p className="text-gray-400 text-sm">Nenhum canal ativo</p>
                  </div>
                </div>
              ) : (
                /* Container com Pizza e Lista */
                <div className="flex items-start gap-4 rounded-lg border border-border/60 bg-background/40 p-3">
                  {/* Gráfico de Pizza Pequeno */}
                  <div className="flex-shrink-0">
                    <PieChart width={120} height={120}>
                        <Pie
                          data={data.channels}
                          dataKey="count"
                          nameKey="name"
                          cx="50%"
                          cy="50%"
                          innerRadius={25}
                          outerRadius={50}
                          paddingAngle={2}
                        >
                          {data.channels.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.color} />
                          ))}
                        </Pie>
                        <Tooltip 
                          contentStyle={{
                            backgroundColor: "var(--popover)",
                            border: "1px solid var(--border)",
                            borderRadius: "8px",
                            color: "var(--popover-foreground)",
                          }}
                          formatter={(value, name) => [
                            `${value} conversas`,
                            name
                          ]}
                        />
                      </PieChart>
                  </div>

                  {/* Lista de Canais */}
                  <div className="flex-1 space-y-2">
                    {data.channels.map((channel, index) => (
                      <div key={index} className="flex items-center justify-between rounded-md px-2 py-1.5 hover:bg-muted/40 transition-colors">
                        <div className="flex items-center gap-3">
                          <div 
                            className="w-3 h-3 rounded-full" 
                            style={{ backgroundColor: channel.color }}
                          />
                          <span className="text-foreground/90">{channel.name}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-foreground font-medium">{channel.count}</span>
                          <span className="text-muted-foreground text-sm">({channel.percentage})</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Volume Diário */}
            <div>
              <h3 className="text-lg font-medium text-foreground mb-4">Volume Diário</h3>
              {data.dailyVolume.length === 0 ? (
                <div className="flex items-center justify-center h-48">
                  <div className="text-center">
                    <div className="text-2xl text-gray-400 mb-1">-</div>
                    <p className="text-gray-400 text-sm">Nenhum dado de volume</p>
                  </div>
                </div>
              ) : (
                <div className="h-48">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={data.dailyVolume} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
                      <XAxis 
                        dataKey="date" 
                        axisLine={false}
                        tickLine={false}
                        tick={{ fill: '#9ca3af', fontSize: 12 }}
                      />
                      <YAxis hide />
                      <Tooltip 
                        contentStyle={{
                          backgroundColor: "var(--popover)",
                          border: "1px solid var(--border)",
                          borderRadius: "8px",
                          color: "var(--popover-foreground)",
                        }}
                        formatter={(value, name) => [
                          `${value} conversas`,
                          'Volume'
                        ]}
                        labelFormatter={(label) => `Data: ${label}`}
                      />
                      <Bar 
                        dataKey="volume" 
                        fill="var(--niochat-bar-neutral)" 
                        radius={[2, 2, 0, 0]}
                        maxBarSize={40}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}