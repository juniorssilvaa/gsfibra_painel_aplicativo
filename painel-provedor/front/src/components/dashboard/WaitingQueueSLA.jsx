import React, { useCallback, useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Clock, AlertTriangle, CheckCircle2, Hourglass, ExternalLink } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { buildApiPath } from "@/utils/apiBaseUrl";

const CHANNEL_LABELS = {
  whatsapp: "WhatsApp",
  whatsapp_oficial: "WhatsApp",
  whatsapp_session: "WhatsApp",
  telegram: "Telegram",
  instagram: "Instagram",
  email: "Email",
  web: "Web",
};

function formatWait(minutes, seconds) {
  const totalSec = typeof seconds === "number" ? seconds : (minutes || 0) * 60;
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  if (h > 0) return `${h}h ${m}min`;
  if (m > 0) return `${m} min`;
  return `${totalSec % 60}s`;
}

function slaStyles(level) {
  if (level === "critico") {
    return {
      row: "border-l-2 border-red-500 bg-red-500/5",
      badge: "bg-red-500/20 text-red-300 border-red-500/40",
      label: "Crítico",
    };
  }
  if (level === "alerta") {
    return {
      row: "border-l-2 border-amber-500 bg-amber-500/5",
      badge: "bg-amber-500/20 text-amber-300 border-amber-500/40",
      label: "Alerta",
    };
  }
  return {
    row: "border-l-2 border-emerald-500/60 bg-transparent",
    badge: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
    label: "No prazo",
  };
}

export default function WaitingQueueSLA({ provedorId }) {
  const navigate = useNavigate();
  const [fila, setFila] = useState({
    total: 0,
    criticos: 0,
    alerta: 0,
    ok: 0,
    sla_alerta_minutos: 5,
    sla_critico_minutos: 15,
    itens: [],
  });
  const [loading, setLoading] = useState(true);

  const fetchFila = useCallback(async () => {
    try {
      const token = localStorage.getItem("auth_token") || localStorage.getItem("token");
      if (!token) {
        setLoading(false);
        return;
      }
      const url = provedorId
        ? buildApiPath(`/api/dashboard/stats/?provedor_id=${provedorId}`)
        : buildApiPath("/api/dashboard/stats/");
      const res = await fetch(url, {
        headers: {
          Authorization: `Token ${token}`,
          "Content-Type": "application/json",
        },
      });
      if (res.ok) {
        const data = await res.json();
        const payload = data.stats?.fila_espera || data.fila_espera;
        if (payload && typeof payload === "object") {
          setFila({
            total: payload.total || 0,
            criticos: payload.criticos || 0,
            alerta: payload.alerta || 0,
            ok: payload.ok || 0,
            sla_alerta_minutos: payload.sla_alerta_minutos || 5,
            sla_critico_minutos: payload.sla_critico_minutos || 15,
            itens: Array.isArray(payload.itens) ? payload.itens : [],
          });
        }
      }
    } catch (err) {
    } finally {
      setLoading(false);
    }
  }, [provedorId]);

  useEffect(() => {
    fetchFila();
    const timer = setInterval(fetchFila, 30000);
    return () => clearInterval(timer);
  }, [fetchFila]);

  const openConversas = () => {
    if (provedorId) {
      navigate(`/app/accounts/${provedorId}/conversas`);
    }
  };

  if (loading) {
    return (
      <Card className="bg-card border-border h-full">
        <CardContent className="p-6 flex items-center justify-center h-48">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="bg-card border-border h-full">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <CardTitle className="text-sm text-foreground flex items-center gap-2">
            <Hourglass className="w-4 h-4 text-primary" />
            Fila de Espera (SLA)
          </CardTitle>
          <button
            type="button"
            onClick={openConversas}
            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            Abrir conversas
            <ExternalLink className="w-3 h-3" />
          </button>
        </div>
        <p className="text-xs text-muted-foreground mt-1">
          Alerta ≥ {fila.sla_alerta_minutos} min · Crítico ≥ {fila.sla_critico_minutos} min
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <div className="rounded-lg border border-border bg-muted/30 px-3 py-2">
            <div className="text-[11px] text-muted-foreground">Na fila</div>
            <div className="text-xl font-semibold text-foreground">{fila.total}</div>
          </div>
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2">
            <div className="text-[11px] text-red-300/80 flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" /> Críticos
            </div>
            <div className="text-xl font-semibold text-red-300">{fila.criticos}</div>
          </div>
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2">
            <div className="text-[11px] text-amber-300/80 flex items-center gap-1">
              <Clock className="w-3 h-3" /> Alerta
            </div>
            <div className="text-xl font-semibold text-amber-300">{fila.alerta}</div>
          </div>
          <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2">
            <div className="text-[11px] text-emerald-300/80 flex items-center gap-1">
              <CheckCircle2 className="w-3 h-3" /> No prazo
            </div>
            <div className="text-xl font-semibold text-emerald-300">{fila.ok}</div>
          </div>
        </div>

        <div className="rounded-md border border-border overflow-hidden">
          <div className="max-h-[280px] overflow-y-auto divide-y divide-border">
            {fila.itens.length === 0 ? (
              <div className="px-4 py-10 text-center text-sm text-muted-foreground">
                Nenhuma conversa aguardando atendimento.
              </div>
            ) : (
              fila.itens.map((item) => {
                const style = slaStyles(item.sla_level);
                const channel =
                  CHANNEL_LABELS[item.channel_type] || item.channel_type || "Canal";
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={openConversas}
                    className={`w-full text-left px-3 py-2.5 hover:bg-muted/40 transition-colors ${style.row}`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="font-medium text-sm text-foreground truncate">
                          {item.contact_name || "Cliente"}
                        </div>
                        <div className="text-xs text-muted-foreground truncate">
                          #{item.id} · {channel}
                          {item.team_name ? ` · ${item.team_name}` : ""}
                        </div>
                      </div>
                      <div className="shrink-0 text-right">
                        <div
                          className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] border ${style.badge}`}
                        >
                          {style.label}
                        </div>
                        <div className="text-xs text-muted-foreground mt-1 tabular-nums">
                          {formatWait(item.waiting_minutes, item.waiting_seconds)}
                        </div>
                      </div>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
