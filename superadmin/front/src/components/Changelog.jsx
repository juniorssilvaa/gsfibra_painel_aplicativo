import React, { useEffect, useState } from 'react'
import { X, Calendar, Package } from 'lucide-react'

export default function Changelog({ isOpen, onClose }) {
  const [versions, setVersions] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!isOpen) return
    const load = async () => {
      try {
        setLoading(true)
        const response = await fetch('/api/changelog/')
        if (!response.ok) return
        const data = await response.json()
        setVersions(Array.isArray(data) ? data : (data?.versions || []))
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [isOpen])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4">
      <div className="bg-card rounded-xl border border-border w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden">
        <div className="flex items-center justify-between p-5 border-b border-border bg-card">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-primary/10 rounded-lg">
              <Package className="w-5 h-5 text-primary" />
            </div>
            <h2 className="text-lg font-semibold text-foreground">Histórico de Versões</h2>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-muted rounded-full transition-colors">
            <X className="w-5 h-5 text-muted-foreground" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="p-8 text-center text-muted-foreground">Carregando...</div>
          ) : (
            <div className="divide-y divide-border">
              {versions.map((v) => (
                <div key={v.version} className="p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-xl font-bold text-foreground">Versão {v.version}</h3>
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Calendar className="w-4 h-4" />
                      <span>{v.date || '-'}</span>
                    </div>
                  </div>
                  <ul className="space-y-2">
                    {(v.changes || []).map((change, idx) => (
                      <li key={idx} className="text-sm text-muted-foreground">
                        - {change.title || change.description || 'Atualização'}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
