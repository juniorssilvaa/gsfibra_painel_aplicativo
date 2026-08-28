import React from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';

export default function ConversationsPieChart({ data }) {
  const chartData = data && data.length > 0 ? data : [];

  if (!chartData || chartData.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="text-center">
          <div className="mb-2 text-4xl text-muted-foreground">-</div>
          <p className="text-muted-foreground">Nenhum dado disponível</p>
        </div>
      </div>
    );
  }

  const themedData = chartData.map((item, idx) => ({
    ...item,
    color: item.color || `hsl(${(idx * 47) % 360} 65% 52%)`,
  }));

  const total = chartData.reduce((sum, d) => sum + d.value, 0);
  // Só desenha fatias com valor > 0 — evita “rabiscos” de categorias zeradas no anel
  const pieSlices = themedData.filter((d) => d.value > 0);

  return (
    <div className="w-full">
      <div className="relative">
        <ResponsiveContainer width="100%" height={280}>
          <PieChart>
            {pieSlices.length > 0 ? (
              <Pie
                data={pieSlices}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={false}
                outerRadius={110}
                innerRadius={60}
                dataKey="value"
                startAngle={90}
                endAngle={-270}
                stroke="none"
                paddingAngle={0}
                isAnimationActive={false}
              >
                {pieSlices.map((entry, index) => (
                  <Cell key={`cell-${entry.name}-${index}`} fill={entry.color} stroke="none" />
                ))}
              </Pie>
            ) : (
              <Pie
                data={[{ name: '_empty', value: 1, color: '#334155' }]}
                cx="50%"
                cy="50%"
                outerRadius={110}
                innerRadius={60}
                dataKey="value"
                stroke="none"
                isAnimationActive={false}
              >
                <Cell fill="#334155" stroke="none" />
              </Pie>
            )}
            <Tooltip
              contentStyle={{
                backgroundColor: 'rgba(15, 23, 42, 0.95)',
                border: '1px solid #1f2a44',
                borderRadius: '8px',
                color: '#cbd5e1',
              }}
            />
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="text-center leading-tight">
            <div className="text-2xl font-bold text-foreground">{total}</div>
            <div className="text-xs text-muted-foreground">Total</div>
          </div>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2">
        {themedData.map((item, index) => (
          <div key={`legend-${item.name}-${index}`} className="flex items-center gap-2">
            <div
              className="h-3 w-3 shrink-0 rounded-full"
              style={{ backgroundColor: item.color }}
            />
            <span className="text-sm font-medium text-foreground">{item.name}</span>
            <span className="text-sm font-medium text-muted-foreground">{item.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
