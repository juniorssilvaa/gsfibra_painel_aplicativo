import React, { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import axios from 'axios';

/**
 * Página intermediária para processar callback OAuth do Meta
 * 
 * Fluxo:
 * 1. Meta redireciona para esta página com code e state
 * 2. Esta página envia code e state para o backend
 * 3. Backend processa e retorna redirect_url
 * 4. Esta página redireciona para /app/accounts/{provider_id}/integracoes
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
      const providerId = state ? state.replace('provider_', '') : '1';
      setError(`Erro na autenticação: ${errorParam}`);
      setTimeout(() => {
        navigate(`/app/accounts/${providerId}/integracoes?oauth_error=${errorParam}`, { replace: true });
      }, 2000);
      return;
    }

    // Validar parâmetros obrigatórios
    if (!code || !state) {
      setError('Parâmetros OAuth inválidos (code ou state ausentes)');
      setTimeout(() => {
        navigate('/app/accounts/1/integracoes?oauth_error=invalid_params', { replace: true });
      }, 2000);
      return;
    }

    // Extrair provider_id do state
    let providerId = '1';
    if (state.startsWith('provider_')) {
      try {
        providerId = state.replace('provider_', '');
      } catch (e) {
        console.error('Erro ao extrair provider_id:', e);
      }
    }

    // Não precisa enviar para o backend - o backend já processou quando recebeu do Meta
    // Apenas redirecionar diretamente para integracoes mantendo code e state
    setStatus('Redirecionando para integrações...');
    
    // Redirecionar diretamente para a página de integrações mantendo code e state
    // O componente Integrations.jsx vai detectar e processar
    const redirectUrl = `/app/accounts/${providerId}/integracoes?code=${code}&state=${state}`;
    console.log('🔵 OAuthCallback - Redirecionando para:', redirectUrl);
    
    // Usar window.location.replace para garantir redirecionamento completo
    // Isso evita que o SafeRedirect interfira e remove a página intermediária do histórico
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

