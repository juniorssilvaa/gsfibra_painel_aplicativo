import React from 'react'

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error) {
    console.error('Superadmin UI error:', error)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-background text-foreground p-6 text-center">
          <div>
            <h1 className="text-2xl font-bold mb-2">Ocorreu um erro</h1>
            <p className="text-muted-foreground">Recarregue a página para tentar novamente.</p>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
