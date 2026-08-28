import React, { useEffect } from 'react'
import { getSuperadminAppBaseUrl } from '../utils/superadminAppUrl'

/**
 * Utilizador autenticado como superadmin no painel provedor:
 * redireciona para a app Superadmin (outra origem) com token no hash (não vai para logs HTTP).
 */
export default function SuperadminHandoffRedirect() {
  const base = getSuperadminAppBaseUrl()

  useEffect(() => {
    const token = localStorage.getItem('auth_token')
    if (token) {
      window.location.replace(`${base}/#niochat_auth_handoff=${encodeURIComponent(token)}`)
    }
  }, [base])

  return (
    <div className="min-h-screen flex items-center justify-center">
      <p className="text-lg text-muted-foreground">A abrir o painel Superadmin…</p>
    </div>
  )
}
