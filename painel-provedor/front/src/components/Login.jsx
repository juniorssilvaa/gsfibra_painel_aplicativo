import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Eye, EyeOff, Lock, User } from 'lucide-react';
import { APP_VERSION } from '../config/version';
import logoImage from '../assets/logo.png';
import { buildApiPath } from '@/utils/apiBaseUrl';
import { getSuperadminAppBaseUrl } from '@/utils/superadminAppUrl';
import { useAuth } from '../contexts/AuthContext';
import { effectiveProvedorFromUser } from '../utils/effectiveProvedorId';
import { friendlyApiError } from '../lib/notify';
import AppNotifyCard from '@/components/ui/AppNotifyCard';
import BlockedScreen from './BlockedScreen';
import {
  emitProvedorPaymentBlocked,
  isProvedorPaymentBlockedError,
} from '../utils/provedorPaymentBlock';

const PROFILE_LOAD_ERROR = 'Não foi possível carregar seu perfil. Tente novamente em instantes.';

export default function Login() {
  const { refresh } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [version, setVersion] = useState(APP_VERSION);
  const [step, setStep] = useState('credentials');
  const [pendingToken, setPendingToken] = useState('');
  const [otpCode, setOtpCode] = useState('');
  const [loginError, setLoginError] = useState('');
  const [paymentBlocked, setPaymentBlocked] = useState(false);

  const showLoginError = (message) => {
    if (!message) return;
    setLoginError(String(message));
  };

  useEffect(() => {
    if (!loginError) return undefined;
    const timer = setTimeout(() => setLoginError(''), 7000);
    return () => clearTimeout(timer);
  }, [loginError]);

  // Buscar versão da API do changelog
  useEffect(() => {
    const fetchVersion = async () => {
      try {
        const changelogUrl = buildApiPath('/api/changelog/');
        const response = await axios.get(changelogUrl);
        if (response.data?.current_version) {
          setVersion(response.data.current_version);
        }
      } catch (err) {
        // Mantém a versão estática como fallback
      }
    };

    fetchVersion();
  }, []);

  const redirectAfterLogin = async (userData, loginUsername) => {
    const isNiohubSupport = String(loginUsername || '').toLowerCase() === 'niohub';
    if (userData.user_type === 'superadmin' && !isNiohubSupport) {
      const base = getSuperadminAppBaseUrl();
      const token = localStorage.getItem('auth_token');
      if (token) {
        window.location.replace(`${base}/#niochat_auth_handoff=${encodeURIComponent(token)}`);
        return;
      }
      navigate('/superadmin', { replace: true });
      return;
    }

    let pid = effectiveProvedorFromUser(userData);
    if (!pid) {
      try {
        const refreshed = await refresh();
        pid = effectiveProvedorFromUser(refreshed);
      } catch {
        /* ignora */
      }
    }

    if (pid) {
      if (userData.user_type === 'agent') {
        navigate(`/${pid}/chat`, { replace: true });
      } else {
        navigate(`/app/accounts/${pid}/dashboard`, { replace: true });
      }
    } else {
      showLoginError('Não foi possível determinar o provedor desta conta. Contacte o suporte.');
    }
  };

  const openBlockedScreen = async () => {
    setPaymentBlocked(true);
    emitProvedorPaymentBlocked();
    await refresh();
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (loading) return;
    setLoading(true);
    setLoginError('');

    try {
      if (step === '2fa') {
        const { data } = await axios.post('/api/auth/2fa/verify-login/', {
          pending_token: pendingToken,
          otp_code: otpCode.trim(),
        });
        if (!data?.token) throw new Error('Token ausente');
        localStorage.setItem('auth_token', data.token);
        if (data.payment_blocked || data.code === 'PROVEDOR_PAYMENT_BLOCKED') {
          await openBlockedScreen();
          return;
        }
        const userData = await refresh();
        if (!userData) {
          showLoginError(PROFILE_LOAD_ERROR);
          return;
        }
        await redirectAfterLogin(userData, username);
        return;
      }

      const loginUrl = buildApiPath('/api/auth/login/');
      const { data } = await axios.post(loginUrl, { username, password });

      if (data?.requires_2fa && data?.pending_token) {
        setPendingToken(data.pending_token);
        setStep('2fa');
        setOtpCode('');
        return;
      }

      if (!data?.token) throw new Error('Token ausente');
      localStorage.setItem('auth_token', data.token);
      if (data.payment_blocked || data.code === 'PROVEDOR_PAYMENT_BLOCKED') {
        await openBlockedScreen();
        return;
      }
      const userData = await refresh();
      if (!userData) {
        showLoginError(PROFILE_LOAD_ERROR);
        return;
      }
      await redirectAfterLogin(userData, username);
    } catch (err) {
      if (isProvedorPaymentBlockedError(err)) {
        emitProvedorPaymentBlocked();
        setPaymentBlocked(true);
        return;
      }
      let message;
      if (step === '2fa') {
        message = friendlyApiError(err, 'Código OTP inválido');
      } else if (err.response?.status === 401) {
        message = 'Usuário ou senha inválidos.';
      } else {
        message = friendlyApiError(err, 'Erro ao conectar com o servidor. Tente novamente.');
      }
      showLoginError(message);
    } finally {
      setLoading(false);
    }
  };

  if (paymentBlocked) {
    return (
      <BlockedScreen
        onLogout={() => {
          localStorage.removeItem('auth_token');
          localStorage.removeItem('token');
          localStorage.removeItem('user');
          setPaymentBlocked(false);
        }}
        fallbackReason="Sua fatura está em atraso. Efetue o pagamento para reativar o acesso ao painel."
      />
    );
  }

  return (
    <div className="min-h-screen bg-zinc-900 flex items-center justify-center p-4 text-white">
      {loginError ? (
        <div className="fixed top-5 right-5 z-[100000] flex justify-end px-4 sm:px-0">
          <AppNotifyCard
            variant="error"
            message={loginError}
            onClose={() => setLoginError('')}
          />
        </div>
      ) : null}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="relative w-full max-w-4xl"
      >
        <div className="bg-zinc-800 rounded-2xl shadow-2xl overflow-hidden border border-zinc-700">
          <div className="flex flex-col md:flex-row">
            <div className="md:w-1/2 bg-zinc-800 px-5 py-8 md:px-6 md:py-10 flex flex-col items-center justify-center relative">
              <div className="absolute inset-0 opacity-[0.03] bg-zinc-200" />
              <div className="relative z-10 flex w-full flex-col items-center justify-center gap-4">
                <img
                  src={logoImage}
                  alt=""
                  className="h-40 w-40 object-contain sm:h-48 sm:w-48 md:h-52 md:w-52"
                />
                <h1 className="login-brand-title text-[2.35rem] font-black uppercase leading-none tracking-[0.18em] sm:text-5xl">
                  NIO HUB
                </h1>
              </div>
            </div>

            <div className="md:w-1/2 p-8 md:p-12 bg-zinc-800">
              <h2 className="text-2xl font-bold text-zinc-100 mb-2 tracking-tight">
                Bem-vindo de volta
              </h2>
              <p className="text-zinc-200 mb-8">
                {step === '2fa'
                  ? 'Informe o código do aplicativo autenticador'
                  : 'Faça login para continuar'}
              </p>

              <form onSubmit={handleSubmit} className="space-y-6">
                {step === 'credentials' ? (
                  <>
                    <div className="space-y-2">
                      <Label className="text-zinc-200">Usuário</Label>
                      <div className="relative">
                        <User className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-zinc-400" />
                        <Input
                          value={username}
                          onChange={(e) => setUsername(e.target.value)}
                          className="pl-12 h-12 bg-zinc-900 border border-zinc-700 text-white placeholder:text-zinc-400 focus:ring-2 focus:ring-primary transition-all"
                          placeholder="Seu usuário"
                          required
                        />
                      </div>
                    </div>

                    <div className="space-y-2">
                      <Label className="text-zinc-200">Senha</Label>
                      <div className="relative">
                        <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-zinc-400" />
                        <Input
                          type={showPassword ? 'text' : 'password'}
                          value={password}
                          onChange={(e) => setPassword(e.target.value)}
                          className="pl-12 pr-12 h-12 bg-zinc-900 border border-zinc-700 text-white placeholder:text-zinc-400 focus:ring-2 focus:ring-primary transition-all"
                          placeholder="Sua senha"
                          required
                        />
                        <button
                          type="button"
                          onClick={() => setShowPassword(!showPassword)}
                          className="absolute right-4 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-white transition-colors"
                        >
                          {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
                        </button>
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="space-y-2">
                    <Label className="text-zinc-200">Código OTP (6 dígitos)</Label>
                    <Input
                      type="text"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      maxLength={6}
                      value={otpCode}
                      onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                      className="h-12 bg-zinc-900 border border-zinc-700 text-white text-center text-xl tracking-[0.4em] font-mono focus:ring-2 focus:ring-primary transition-all"
                      placeholder="000000"
                      required
                      autoFocus
                    />
                    <button
                      type="button"
                      className="text-sm text-zinc-400 hover:text-white"
                      onClick={() => {
                        setStep('credentials');
                        setPendingToken('');
                        setOtpCode('');
                      }}
                    >
                      Voltar ao login
                    </button>
                  </div>
                )}

                <Button type="submit" disabled={loading} className="w-full h-12 bg-primary hover:bg-primary/90 text-primary-foreground font-semibold transition-all">
                  {loading
                    ? 'Entrando...'
                    : step === '2fa'
                      ? 'Confirmar código'
                      : 'Acessar'}
                </Button>
              </form>
            </div>
          </div>
        </div>

        <div className="text-center mt-6 text-sm text-zinc-400 space-y-1">
          <p>© 2026 NIO HUB</p>
          <p>Versão {version}</p>
        </div>
      </motion.div>
    </div>
  );
}
