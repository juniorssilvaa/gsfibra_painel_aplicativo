import React from 'react';
import { Card, CardContent } from "@/components/ui/card";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

export default function MetricCard({ 
  title, 
  value, 
  change, 
  trend, 
  icon: Icon, 
  subtitle,
  color // Adicionando suporte a cor
}) {
  const TrendIcon = trend === 'up' ? TrendingUp : trend === 'down' ? TrendingDown : Minus;
  const trendColor = trend === 'up' ? 'text-emerald-400' : trend === 'down' ? 'text-rose-400' : 'text-slate-400';

  // Mapeamento de cores para classes do Tailwind
  const colorClasses = {
    'text-blue-500': 'border-blue-500/30 bg-blue-500/5',
    'text-green-500': 'border-green-500/30 bg-green-500/5',
    'text-purple-500': 'border-purple-500/30 bg-purple-500/5',
    'text-orange-500': 'border-orange-500/30 bg-orange-500/5',
    'text-yellow-500': 'border-yellow-500/30 bg-yellow-500/5',
  };

  const colorStyle = colorClasses[color] || 'border-border bg-card';
  const iconColor = color || 'text-primary';

  return (
    <Card className={`hover:shadow-lg transition-all duration-200 border ${colorStyle}`}>
      <CardContent className="p-5">
        <div className="flex items-center justify-between">
          <div className="space-y-2">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">{title}</p>
            <div className="flex items-end gap-2">
              <h3 className="text-2xl font-bold text-foreground">{value}</h3>
              {subtitle && <span className="text-[11px] text-muted-foreground mb-[2px]">{subtitle}</span>}
            </div>
            {change && (
              <div className={`flex items-center gap-1 text-xs font-medium ${trendColor}`}>
                <TrendIcon className="w-3.5 h-3.5" />
                <span>{change}</span>
              </div>
            )}
          </div>
          <div className={`p-3 rounded-xl bg-background/50 border border-border shadow-inner`}>
            <Icon className={`w-6 h-6 ${iconColor}`} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
