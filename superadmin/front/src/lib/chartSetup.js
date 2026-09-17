/**
 * Registro completo do Chart.js antes de qualquer gráfico.
 * `chart.js/auto` registra ArcElement, controllers, scales, etc.
 */
import 'chart.js/auto';

export function ensureChartJsRegistered() {
  // no-op: side-effect do import acima
}
