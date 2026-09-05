/**
 * Registro único dos componentes Chart.js (tree-shaking).
 * Evita "arc is not a registered element" ao renderizar Pie/Doughnut.
 */
import {
  Chart as ChartJS,
  ArcElement,
  Tooltip,
  Legend,
  PieController,
  DoughnutController,
  CategoryScale,
  LinearScale,
  BarElement,
  BarController,
  LineElement,
  LineController,
  PointElement,
  Title,
} from 'chart.js';

let registered = false;

export function ensureChartJsRegistered() {
  if (registered) return;
  ChartJS.register(
    ArcElement,
    Tooltip,
    Legend,
    PieController,
    DoughnutController,
    CategoryScale,
    LinearScale,
    BarElement,
    BarController,
    LineElement,
    LineController,
    PointElement,
    Title,
  );
  registered = true;
}

ensureChartJsRegistered();
