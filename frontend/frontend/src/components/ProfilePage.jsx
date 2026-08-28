import React, { useState, useEffect, useRef } from 'react';
import { User, Shield, Bell, Volume2, Save, Key, Settings, MessageSquare } from 'lucide-react';
import axios from 'axios';
import useSessionTimeout from '../hooks/useSessionTimeout';
import { useLanguage } from '../contexts/LanguageContext';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from './ui/dialog';
import { Input } from './ui/input';
import { Label } from './ui/label';

export default function ProfilePage() {
  const [activeTab, setActiveTab] = useState('profile');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState('success'); // 'success' ou 'error'
  const [userData, setUserData] = useState(null);
  const audioRef = useRef(null);
  const { updateTimeout } = useSessionTimeout();
  const { language, changeLanguage, t } = useLanguage();
  // Sons disponíveis - carregados dinamicamente
  const [availableSounds, setAvailableSounds] = useState([]);
  const [messageSounds, setMessageSounds] = useState([]);
  const [conversationSounds, setConversationSounds] = useState([]);
  const [settings, setSettings] = useState({
    profile: {
      name: '',
      email: '',
      phone: '',
      avatar: null,
      language: 'pt'
    },
    notifications: {
      soundNotifications: false,
      newMessageSound: '01.mp3',
      newMessageVolume: 1.0,
      newConversationSound: '02.mp3',
      newConversationVolume: 1.0
    },
    security: {
      twoFactorAuth: false,
      sessionTimeout: 30
    },
    assignment: {
      message: ''
    }
  });
  const [showResetPasswordModal, setShowResetPasswordModal] = useState(false);
  const [resetPasswordNew, setResetPasswordNew] = useState('');
  const [resetPasswordConfirm, setResetPasswordConfirm] = useState('');
  const [resetPasswordError, setResetPasswordError] = useState('');

  // Carregar sons disponíveis
  useEffect(() => {
    const loadAvailableSounds = async () => {
      try {
        // Lista de sons disponíveis baseada nos arquivos na pasta /sounds (01.mp3 até 14.mp3)
        const allSounds = Array.from({ length: 14 }, (_, i) => {
          const num = (i + 1).toString().padStart(2, '0');
          return `${num}.mp3`;
        });

        setAvailableSounds(allSounds);
        setMessageSounds(allSounds); // Usar os mesmos sons para ambos
        setConversationSounds(allSounds);
      } catch (error) {
        console.error('Erro ao carregar sons:', error);
      }
    };

    loadAvailableSounds();
  }, []);

  // Buscar dados do usuário
  useEffect(() => {
    const fetchUserData = async () => {
      try {
        const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
        const response = await axios.get('/api/auth/me/', {
          headers: { Authorization: `Token ${token}` }
        });

        const user = response.data;
        setUserData(user);
        const storedSoundEnabled = localStorage.getItem('sound_notifications_enabled');
        const storedMsgSound = localStorage.getItem('sound_new_message');
        const storedConvSound = localStorage.getItem('sound_new_conversation');
        const userLanguage = user.language || 'pt';

        setSettings({
          ...settings,
          profile: {
            name: `${user.first_name || ''} ${user.last_name || ''}`.trim() || user.username,
            email: user.email || '',
            phone: user.phone || '',
            avatar: user.avatar,
            language: userLanguage
          },
          notifications: {
            ...settings.notifications,
            soundNotifications: typeof user.sound_notifications_enabled === 'boolean'
              ? user.sound_notifications_enabled
              : (storedSoundEnabled ? storedSoundEnabled === 'true' : settings.notifications.soundNotifications),
            newMessageSound: user.new_message_sound || storedMsgSound || settings.notifications.newMessageSound,
            newMessageVolume: user.new_message_sound_volume !== undefined ? user.new_message_sound_volume : settings.notifications.newMessageVolume,
            newConversationSound: user.new_conversation_sound || storedConvSound || settings.notifications.newConversationSound,
            newConversationVolume: user.new_conversation_sound_volume !== undefined ? user.new_conversation_sound_volume : settings.notifications.newConversationVolume
          },
          security: {
            ...settings.security,
            sessionTimeout: user.session_timeout || settings.security.sessionTimeout
          },
          assignment: {
            message: user.assignment_message || ''
          }
        });
      } catch (error) {
        console.error('Erro ao buscar dados do usuário:', error);
      }
    };

    fetchUserData();
  }, []);

  // Idioma só será atualizado quando salvar, não quando selecionar

  const handleSaveProfile = async () => {
    setLoading(true);
    setMessage('');

    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const [firstName, ...lastNameParts] = settings.profile.name.split(' ');
      const lastName = lastNameParts.join(' ') || '';

      await axios.patch('/api/auth/me/', {
        first_name: firstName,
        last_name: lastName,
        email: settings.profile.email,
        phone: settings.profile.phone,
        session_timeout: settings.security.sessionTimeout,
        language: settings.profile.language,
        assignment_message: settings.assignment.message
      }, {
        headers: { Authorization: `Token ${token}` }
      });

      // Atualizar idioma no contexto
      if (settings.profile.language !== language) {
        changeLanguage(settings.profile.language);
      }

      // Atualizar timeout da sessão
      try {
        await axios.patch('/api/auth/me/', {
          session_timeout: settings.security.sessionTimeout
        }, {
          headers: { Authorization: `Token ${token}` }
        });

        // Atualizar o timeout no frontend
        await updateTimeout();
      } catch (error) {
        console.error('Erro ao atualizar timeout da sessão:', error);
      }

      setMessage(t('perfil_atualizado'));
      setMessageType('success');
      setTimeout(() => {
        setMessage('');
        setMessageType('success');
      }, 3000);
    } catch (error) {
      console.error('Erro ao atualizar perfil:', error);
      setMessage(t('erro_atualizar'));
      setMessageType('error');
      setTimeout(() => {
        setMessage('');
        setMessageType('success');
      }, 3000);
    } finally {
      setLoading(false);
    }
  };

  const formatSoundLabel = (fileName) => {
    // Remover extensão e prefixos, formatar nome
    let base = fileName.replace(/\.(mp3|wav)$/i, '');

    // Remover prefixos específicos
    base = base.replace(/^(message_in_|chat_new_)/, '');

    // Converter para formato legível
    base = base.replace(/_/g, ' ');

    // Capitalizar primeira letra
    return base.charAt(0).toUpperCase() + base.slice(1);
  };

  const handleToggleSoundNotifications = async (checked) => {
    setSettings({
      ...settings,
      notifications: { ...settings.notifications, soundNotifications: checked }
    });
    localStorage.setItem('sound_notifications_enabled', String(checked));
    // Disparar evento para o NotificationContext
    window.dispatchEvent(new CustomEvent('notification-settings-updated'));

    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      await axios.patch('/api/auth/me/', {
        sound_notifications_enabled: checked
      }, {
        headers: { Authorization: `Token ${token}` }
      });
    } catch (e) {
      console.error('Erro ao salvar preferência de som no servidor:', e);
    }
  };

  const handleSelectSound = async (type, value) => {
    setSettings({
      ...settings,
      notifications: { ...settings.notifications, [type]: value }
    });
    if (type === 'newMessageSound') {
      localStorage.setItem('sound_new_message', value);
    }
    if (type === 'newConversationSound') {
      localStorage.setItem('sound_new_conversation', value);
    }
    // Disparar evento para o NotificationContext
    window.dispatchEvent(new CustomEvent('notification-settings-updated'));
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      await axios.patch('/api/auth/me/', {
        [type === 'newMessageSound' ? 'new_message_sound' : 'new_conversation_sound']: value
      }, {
        headers: { Authorization: `Token ${token}` }
      });
    } catch (e) {
      console.error('Erro ao salvar som no servidor:', e);
    }
  };

  const handleVolumeChange = async (type, value) => {
    const volume = parseFloat(value);
    setSettings({
      ...settings,
      notifications: { ...settings.notifications, [type]: volume }
    });
    
    // Salvar volume no localStorage para atualização imediata
    localStorage.setItem(type === 'newMessageVolume' ? 'sound_new_message_volume' : 'sound_new_conversation_volume', volume.toString());
    
    // Disparar evento para o NotificationContext
    window.dispatchEvent(new CustomEvent('notification-settings-updated'));

    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      await axios.patch('/api/auth/me/', {
        [type === 'newMessageVolume' ? 'new_message_sound_volume' : 'new_conversation_sound_volume']: volume
      }, {
        headers: { Authorization: `Token ${token}` }
      });
    } catch (e) {
      console.error('Erro ao salvar volume no servidor:', e);
    }
  };

  const handlePreviewSound = async (fileName, volume = 1.0) => {
    try {
      if (!fileName) {
        console.warn('Nenhum arquivo de som selecionado');
        return;
      }

      const src = `/sounds/${fileName}`;


      // Verificar se o arquivo existe fazendo uma requisição HEAD
      try {
        const response = await fetch(src, { method: 'HEAD' });
        if (!response.ok) {
          throw new Error(`Arquivo não encontrado: ${src} (Status: ${response.status})`);
        }

      } catch (fetchError) {
        console.error('Erro ao verificar arquivo:', fetchError);
        alert(`Arquivo de som não encontrado: ${fileName}`);
        return;
      }

      // Pausar som atual se estiver tocando
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current.currentTime = 0;
      }

      // Criar novo elemento de áudio
      const audio = new Audio(src);
      audio.volume = volume;
      audioRef.current = audio;

      // Configurar eventos de erro
      audio.onerror = (e) => {
        console.error('Erro ao carregar arquivo de som:', e);
        alert('Erro ao carregar arquivo de som. Verifique se o arquivo existe.');
      };





      // Tentar reproduzir
      await audio.play();

    } catch (error) {
      console.error('Erro ao reproduzir som:', error);
      if (error.name === 'NotAllowedError') {
        alert('Reprodução de áudio bloqueada pelo navegador. Clique em qualquer lugar da página e tente novamente.');
      } else if (error.name === 'NotSupportedError') {
        alert('Formato de arquivo não suportado ou arquivo não encontrado.');
      } else {
        alert('Erro ao reproduzir som: ' + error.message);
      }
    }
  };

  const openResetPasswordModal = () => {
    setResetPasswordNew('');
    setResetPasswordConfirm('');
    setResetPasswordError('');
    setShowResetPasswordModal(true);
  };

  const closeResetPasswordModal = () => {
    setShowResetPasswordModal(false);
    setResetPasswordNew('');
    setResetPasswordConfirm('');
    setResetPasswordError('');
  };

  const handleResetPassword = async (e) => {
    e?.preventDefault();
    setResetPasswordError('');
    const newPassword = resetPasswordNew.trim();
    const confirmPassword = resetPasswordConfirm.trim();
    if (!newPassword) {
      setResetPasswordError('Digite sua nova senha.');
      return;
    }
    if (!confirmPassword) {
      setResetPasswordError('Confirme sua nova senha.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setResetPasswordError('As senhas não coincidem.');
      return;
    }
    setLoading(true);
    setMessage('');
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      await axios.post('/api/users/reset-password/', {
        new_password: newPassword
      }, {
        headers: { Authorization: `Token ${token}` }
      });
      setMessage('Senha alterada com sucesso!');
      setMessageType('success');
      closeResetPasswordModal();
      setTimeout(() => {
        setMessage('');
        setMessageType('success');
      }, 3000);
    } catch (error) {
      console.error('Erro ao alterar senha:', error);
      const msg = error.response?.data?.error || error.response?.data?.detail || 'Erro ao alterar senha. Tente novamente.';
      setResetPasswordError(typeof msg === 'string' ? msg : 'Erro ao alterar senha. Tente novamente.');
    } finally {
      setLoading(false);
    }
  };

  const tabs = [
    { id: 'profile', label: t('perfil'), icon: User },
    { id: 'notifications', label: t('notificacoes'), icon: Bell },
    { id: 'security', label: t('seguranca'), icon: Shield },
    { id: 'assignment', label: t('atribuicao') || 'Atribuição', icon: MessageSquare }
  ];

  const renderAssignmentSettings = () => (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-medium text-white">
          {t('mensagem_atribuicao') || 'Mensagem de Atribuição'}
        </h3>
        <button
          onClick={handleSaveProfile}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Save className="w-4 h-4" />
          {loading ? t('salvando') : t('salvar')}
        </button>
      </div>

      <div className="p-4 border border-border rounded-lg">
        <textarea
          value={settings.assignment.message}
          onChange={(e) => setSettings({
            ...settings,
            assignment: { ...settings.assignment, message: e.target.value }
          })}
          className="niochat-input w-full min-h-[150px] p-3"
          placeholder={t('digite_mensagem_atribuicao') || 'Digite sua mensagem de atribuição aqui...'}
        />
      </div>
    </div>
  );

  const renderProfileSettings = () => (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-medium text-white">
          {t('informacoes_pessoais')}
        </h3>
        <button
          onClick={handleSaveProfile}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Save className="w-4 h-4" />
          {loading ? t('salvando') : t('salvar')}
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-white mb-2">
            {t('nome_completo')}
          </label>
          <input
            type="text"
            value={settings.profile.name}
            onChange={(e) => setSettings({
              ...settings,
              profile: { ...settings.profile, name: e.target.value }
            })}
            className="niochat-input"
            placeholder={t('nome_completo')}
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-white mb-2">
            {t('email')}
          </label>
          <input
            type="email"
            value={settings.profile.email}
            onChange={(e) => setSettings({
              ...settings,
              profile: { ...settings.profile, email: e.target.value }
            })}
            className="niochat-input"
            placeholder={t('email')}
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-white mb-2">
            {t('telefone')}
          </label>
          <input
            type="tel"
            value={settings.profile.phone}
            onChange={(e) => setSettings({
              ...settings,
              profile: { ...settings.profile, phone: e.target.value }
            })}
            className="niochat-input"
            placeholder={t('telefone')}
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-white mb-2">
            {t('idioma_sistema')}
          </label>
          <select
            value={settings.profile.language}
            onChange={(e) => {
              const newLanguage = e.target.value;
              setSettings({
                ...settings,
                profile: { ...settings.profile, language: newLanguage }
              });
              // Idioma só será salvo quando clicar em Salvar
            }}
            className="niochat-input"
          >
            <option value="pt">Português</option>
            <option value="en">English</option>
            <option value="es">Español</option>
            <option value="fr">Français</option>
            <option value="de">Deutsch</option>
            <option value="it">Italiano</option>
          </select>
        </div>
      </div>
    </div>
  );

  const renderNotificationSettings = () => (
    <div className="space-y-6">
      <h3 className="text-lg font-medium text-white mb-4">
        {t('preferencias_notificacao')}
      </h3>
      <div className="space-y-4">
        <div className="flex items-center justify-between p-4 border border-border rounded-lg">
          <div className="flex items-center gap-2">
            <Volume2 className="w-5 h-5 text-white/70" />
            <h4 className="font-medium text-white">{t('notificacoes_sonoras')}</h4>
          </div>
          <label className="relative inline-flex items-center cursor-pointer">
            <input
              type="checkbox"
              checked={settings.notifications.soundNotifications}
              onChange={(e) => handleToggleSoundNotifications(e.target.checked)}
              className="sr-only peer"
            />
            <div className="w-11 h-6 bg-red-500/80 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-green-500/20 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-green-500"></div>
          </label>
        </div>
      </div>
      {settings.notifications.soundNotifications && (
        <div className="space-y-4">
          <div className="p-4 border border-border rounded-lg">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
              <div className="md:col-span-2">
                <label className="block text-sm font-medium text-white mb-2">
                  {t('som_novas_mensagens')}
                </label>
                <select
                  value={settings.notifications.newMessageSound}
                  onChange={(e) => handleSelectSound('newMessageSound', e.target.value)}
                  className="niochat-input"
                >
                  {messageSounds.length > 0 ? messageSounds.map((s) => (
                    <option key={s} value={s}>{formatSoundLabel(s)}</option>
                  )) : (
                    <option value="">Carregando sons...</option>
                  )}
                </select>

                <div className="mt-4">
                  <div className="flex justify-between items-center mb-1">
                    <label className="block text-xs font-medium text-white/70">
                      Volume
                    </label>
                    <span className="text-xs font-medium text-primary">
                      {Math.round(settings.notifications.newMessageVolume * 100)}%
                    </span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.01"
                    value={settings.notifications.newMessageVolume}
                    onChange={(e) => handleVolumeChange('newMessageVolume', e.target.value)}
                    className="w-full h-1.5 bg-white/10 rounded-lg appearance-none cursor-pointer accent-primary"
                    style={{
                      backgroundImage: `linear-gradient(to right, #fff 0%, #fff ${settings.notifications.newMessageVolume * 100}%, transparent ${settings.notifications.newMessageVolume * 100}%, transparent 100%)`
                    }}
                  />
                </div>
              </div>
              <div className="pb-1">
                <button
                  type="button"
                  onClick={() => handlePreviewSound(settings.notifications.newMessageSound, settings.notifications.newMessageVolume)}
                  className="w-full px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 flex items-center justify-center gap-2 transition-colors"
                >
                  <Volume2 className="w-4 h-4" />
                  {t('reproduzir')}
                </button>
              </div>
            </div>
          </div>
          <div className="p-4 border border-border rounded-lg">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
              <div className="md:col-span-2">
                <label className="block text-sm font-medium text-white mb-2">
                  {t('som_novas_conversas')}
                </label>
                <select
                  value={settings.notifications.newConversationSound}
                  onChange={(e) => handleSelectSound('newConversationSound', e.target.value)}
                  className="niochat-input"
                >
                  {conversationSounds.length > 0 ? conversationSounds.map((s) => (
                    <option key={s} value={s}>{formatSoundLabel(s)}</option>
                  )) : (
                    <option value="">Carregando sons...</option>
                  )}
                </select>

                <div className="mt-4">
                  <div className="flex justify-between items-center mb-1">
                    <label className="block text-xs font-medium text-white/70">
                      Volume
                    </label>
                    <span className="text-xs font-medium text-primary">
                      {Math.round(settings.notifications.newConversationVolume * 100)}%
                    </span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.01"
                    value={settings.notifications.newConversationVolume}
                    onChange={(e) => handleVolumeChange('newConversationVolume', e.target.value)}
                    className="w-full h-1.5 bg-white/10 rounded-lg appearance-none cursor-pointer accent-primary"
                    style={{
                      backgroundImage: `linear-gradient(to right, #fff 0%, #fff ${settings.notifications.newConversationVolume * 100}%, transparent ${settings.notifications.newConversationVolume * 100}%, transparent 100%)`
                    }}
                  />
                </div>
              </div>
              <div className="pb-1">
                <button
                  type="button"
                  onClick={() => handlePreviewSound(settings.notifications.newConversationSound, settings.notifications.newConversationVolume)}
                  className="w-full px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 flex items-center justify-center gap-2 transition-colors"
                >
                  <Volume2 className="w-4 h-4" />
                  {t('reproduzir')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );

  const renderSecuritySettings = () => (
    <div className="space-y-6">
      <h3 className="text-lg font-medium text-white mb-4">
        {t('configuracoes_seguranca')}
      </h3>
      <div className="space-y-4">
        <div className="p-4 border border-border rounded-lg">
          <div className="flex items-center justify-between">
            <div>
              <h4 className="font-medium text-white">{t('autenticacao_dois_fatores')}</h4>
              <p className="text-sm text-white/70">
                {t('adicionar_camada_seguranca')}
              </p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={settings.security.twoFactorAuth}
                onChange={(e) => setSettings({
                  ...settings,
                  security: { ...settings.security, twoFactorAuth: e.target.checked }
                })}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-red-500/80 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-green-500/20 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-green-500"></div>
            </label>
          </div>
        </div>

        <div className="p-4 border border-border rounded-lg">
          <div className="flex items-center justify-between">
            <div>
              <h4 className="font-medium text-white">{t('redefinir_senha')}</h4>
              <p className="text-sm text-white/70">
                {t('alterar_senha')}
              </p>
            </div>
            <button
              onClick={openResetPasswordModal}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2 bg-orange-500 text-white rounded-lg hover:bg-orange-600 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Key className="w-4 h-4" />
              {t('alterar')}
            </button>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-white mb-2">
            {t('timeout_sessao')}
          </label>
          <div className="flex gap-2">
            <select
              value={settings.security.sessionTimeout}
              onChange={(e) => setSettings({
                ...settings,
                security: { ...settings.security, sessionTimeout: parseInt(e.target.value) }
              })}
              className="niochat-input flex-1"
            >
              <option value={1}>1 minuto</option>
              <option value={2}>2 minutos</option>
              <option value={15}>15 minutos</option>
              <option value={30}>30 minutos</option>
              <option value={60}>1 hora</option>
              <option value={120}>2 horas</option>
            </select>
            <button
              onClick={handleSaveProfile}
              disabled={loading}
              className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Save className="w-4 h-4" />
              {loading ? t('salvando') : t('salvar')}
            </button>
          </div>
        </div>
      </div>
    </div>
  );

  const renderTabContent = () => {
    switch (activeTab) {
      case 'profile':
        return renderProfileSettings();
      case 'notifications':
        return renderNotificationSettings();
      case 'security':
        return renderSecuritySettings();
      case 'assignment':
        return renderAssignmentSettings();
      default:
        return null;
    }
  };

  return (
    <div className="flex-1 p-6 bg-background overflow-y-auto">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold text-foreground mb-6 flex items-center gap-3">
          <User className="w-8 h-8 text-white/70" /> {t('perfil')}
        </h1>

        {/* Mensagem de feedback global */}
        {message && (
          <div className={`mb-4 p-4 rounded-lg border ${messageType === 'success'
            ? 'bg-green-50 text-green-800 border-green-200 dark:bg-green-900/20 dark:text-green-400 dark:border-green-800'
            : 'bg-red-50 text-red-800 border-red-200 dark:bg-red-900/20 dark:text-red-400 dark:border-red-800'
            }`}>
            <div className="flex items-center gap-2">
              {messageType === 'success' ? (
                <svg className="w-5 h-5 text-green-600" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                </svg>
              ) : (
                <svg className="w-5 h-5 text-red-600" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
              )}
              <span className="font-medium">{message}</span>
            </div>
          </div>
        )}

        <div className="flex flex-col lg:flex-row gap-6">
          {/* Sidebar */}
          <div className="lg:w-64">
            <nav className="space-y-2">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`w-full flex items-center space-x-3 px-4 py-3 rounded-lg text-left transition-colors ${activeTab === tab.id
                    ? 'bg-primary text-primary-foreground'
                    : 'text-white/70 hover:text-foreground hover:bg-muted'
                    }`}
                >
                  <tab.icon className="w-5 h-5" />
                  <span>{tab.label}</span>
                </button>
              ))}
            </nav>
          </div>

          {/* Content */}
          <div className="flex-1">
            <div className="niochat-card p-6">
              {renderTabContent()}
            </div>
          </div>
        </div>
      </div>

      {/* Modal Redefinir Senha */}
      <Dialog open={showResetPasswordModal} onOpenChange={(open) => !open && closeResetPasswordModal()}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t('redefinir_senha')}</DialogTitle>
            <DialogDescription>{t('alterar_senha')}</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleResetPassword} className="space-y-4">
            {resetPasswordError && (
              <div className="p-3 rounded-lg bg-red-50 text-red-800 border border-red-200 dark:bg-red-900/20 dark:text-red-400 dark:border-red-800 text-sm">
                {resetPasswordError}
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="reset-new-password">{t('nova_senha') || 'Nova senha'}</Label>
              <Input
                id="reset-new-password"
                type="password"
                value={resetPasswordNew}
                onChange={(e) => setResetPasswordNew(e.target.value)}
                placeholder={t('nova_senha') || 'Nova senha'}
                className="w-full"
                autoComplete="new-password"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="reset-confirm-password">{t('confirme_senha') || 'Confirme sua nova senha'}</Label>
              <Input
                id="reset-confirm-password"
                type="password"
                value={resetPasswordConfirm}
                onChange={(e) => setResetPasswordConfirm(e.target.value)}
                placeholder={t('confirme_senha') || 'Confirme sua nova senha'}
                className="w-full"
                autoComplete="new-password"
              />
            </div>
            <DialogFooter>
              <button
                type="button"
                onClick={closeResetPasswordModal}
                className="px-4 py-2 rounded-lg border border-input bg-background hover:bg-accent"
              >
                {t('cancelar') || 'Cancelar'}
              </button>
              <button
                type="submit"
                disabled={loading}
                className="flex items-center gap-2 px-4 py-2 bg-orange-500 text-white rounded-lg hover:bg-orange-600 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Key className="w-4 h-4" />
                {loading ? t('alterando') : t('alterar')}
              </button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
} 