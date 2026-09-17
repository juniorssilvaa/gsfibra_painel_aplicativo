import React from 'react';

/**
 * Isola falhas de gráfico para não derrubar o dashboard inteiro.
 */
export default class ChartErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error) {
    console.warn('[ChartErrorBoundary]', error?.message || error);
  }

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback || (
          <div className="rounded-xl border border-border bg-card/50 p-6 text-center text-sm text-muted-foreground">
            Gráfico indisponível no momento.
          </div>
        )
      );
    }
    return this.props.children;
  }
}
