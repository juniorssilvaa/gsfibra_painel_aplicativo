import React, { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';

/**
 * Página intermediária para processar callback OAuth do Meta no Superadmin
 * 
 * Fluxo:
 * 1. Meta redireciona para esta página com code e state
 * 2. Esta página redireciona para /app/meta/finalizando-superadmin
 */
function OAuthCallback() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState('Processando autenticação...');
  const [error, setError] = useState(null);

  useEffect(() => {
    const code = searchParams.get('code');
    const state = searchParams.get('state');
    const errorParam = searchParams.get('error');

    // Se houver erro do OAuth
    if (errorParam) {
      setError(`Erro na autenticação: ${errorParam}`);
      setTimeout(() => {
        navigate(`/admin/configuracoes?oauth_error=${errorParam}`, { replace: true });
      }, 2000);
      return;
    }

    // Validar parâmetros obrigatórios
    if (!code || !state) {
      setError('Parâmetros OAuth inválidos (code ou state ausentes)');
      setTimeout(() => {
        navigate('/admin/configuracoes?oauth_error=invalid_params', { replace: true });
      }, 2000);
      return;
    }

    setStatus('Redirecionando para finalização...');
    
    // Redirecionar diretamente para a página de finalização mantendo code e state
    const redirectUrl = `/app/meta/finalizando-superadmin?code=${code}&state=${state}`;
    console.log('🔵 OAuthCallback Superadmin - Redirecionando para:', redirectUrl);
    
    // Usar window.location.replace para garantir redirecionamento completo
    setTimeout(() => {
      window.location.replace(redirectUrl);
    }, 500);
  }, [searchParams, navigate]);

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'center',
      alignItems: 'center',
      height: '100vh',
      backgroundColor: '#1a1b2e',
      color: '#ffffff',
      fontFamily: 'system-ui, -apple-system, sans-serif'
    }}>
      <div style={{
        textAlign: 'center',
        padding: '2rem',
        backgroundColor: '#23243a',
        borderRadius: '12px',
        boxShadow: '0 4px 6px rgba(0, 0, 0, 0.3)',
        maxWidth: '500px',
        width: '90%'
      }}>
        {error ? (
          <>
            <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>❌</div>
            <h2 style={{ marginBottom: '1rem', color: '#ff6b6b' }}>Erro na Autenticação</h2>
            <p style={{ color: '#a0a0a0', marginBottom: '2rem' }}>{error}</p>
            <p style={{ color: '#666', fontSize: '0.9rem' }}>Redirecionando...</p>
          </>
        ) : (
          <>
            <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>⏳</div>
            <h2 style={{ marginBottom: '1rem' }}>Processando Autenticação</h2>
            <p style={{ color: '#a0a0a0', marginBottom: '2rem' }}>{status}</p>
            <div style={{
              width: '100%',
              height: '4px',
              backgroundColor: '#35365a',
              borderRadius: '2px',
              overflow: 'hidden',
              marginTop: '1rem'
            }}>
              <div style={{
                width: '100%',
                height: '100%',
                backgroundColor: '#4a9eff',
                animation: 'pulse 1.5s ease-in-out infinite'
              }}></div>
            </div>
          </>
        )}
      </div>
      
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 0.6; }
          50% { opacity: 1; }
        }
      `}</style>
    </div>
  );
}

export default OAuthCallback;
