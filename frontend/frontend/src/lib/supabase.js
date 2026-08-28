import { createClient } from '@supabase/supabase-js'

// Configurações do Supabase
// Tentar ler das variáveis de ambiente do Vite (com prefixo VITE_)
// Se não encontrar, tentar ler diretamente do backend via import.meta.env
// Isso permite que o .env do backend seja usado diretamente
let supabaseUrl = import.meta.env.VITE_SUPABASE_URL 
  || import.meta.env.SUPABASE_URL 
  || '';
  
let supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY 
  || import.meta.env.SUPABASE_ANON_KEY 
  || '';

// Declarar variável supabase antes de ser usada
let supabase = null;

// Função para criar o cliente Supabase
const createSupabaseClient = () => {
  if (supabaseUrl && supabaseUrl.trim() !== '' && supabaseAnonKey && supabaseAnonKey.trim() !== '') {
    try {
      supabase = createClient(supabaseUrl, supabaseAnonKey, {
        realtime: {
          params: {
            eventsPerSecond: 10
          }
        }
      });
      
      // Salvar no localStorage para uso futuro
      if (typeof window !== 'undefined') {
        localStorage.setItem('supabase_url', supabaseUrl);
        localStorage.setItem('supabase_anon_key', supabaseAnonKey);
      }
      
      return true;
    } catch (error) {
      return false;
    }
  }
  return false;
};

// Função para inicializar o Supabase buscando configurações do backend se necessário
const initializeSupabase = async () => {
  // Se já tem as variáveis e o cliente foi criado, não precisa buscar
  if (supabaseUrl && supabaseAnonKey && supabase) {
    return;
  }
  
  // Se não encontrou as variáveis, tentar buscar do backend via API
  // (para desenvolvimento local quando o .env não está acessível)
  if (typeof window !== 'undefined') {
    // Tentar buscar do localStorage (pode ter sido salvo anteriormente)
    const storedUrl = localStorage.getItem('supabase_url');
    const storedKey = localStorage.getItem('supabase_anon_key');
    
    if (storedUrl && storedKey) {
      supabaseUrl = storedUrl;
      supabaseAnonKey = storedKey;
      createSupabaseClient();
      return;
    }
    
    // Tentar buscar do endpoint de configuração do backend
    try {
      const response = await fetch('/api/supabase-config/');
      if (response.ok) {
        const config = await response.json();
        if (config.supabase_url && config.supabase_anon_key) {
          supabaseUrl = config.supabase_url;
          supabaseAnonKey = config.supabase_anon_key;
          // Salvar no localStorage para próxima vez
          localStorage.setItem('supabase_url', supabaseUrl);
          localStorage.setItem('supabase_anon_key', supabaseAnonKey);
          // Criar o cliente após obter as configurações
          createSupabaseClient();
        }
      }
    } catch (err) {
      // Usar fallback padrão se disponível
      const defaultUrl = 'https://uousrmdefljusigvncrb.supabase.co';
      if (!supabaseUrl && defaultUrl) {
        supabaseUrl = defaultUrl;
      }
    }
  }
};

// Inicializar imediatamente (assíncrono, mas não bloqueia)
if (typeof window !== 'undefined') {
  initializeSupabase();
}

// Validar se as variáveis estão definidas (sem logs)

// Criar cliente Supabase inicial (se já tiver as variáveis)
createSupabaseClient();

// Se não conseguiu criar, tentar buscar do backend (sem logs)

// Função helper para garantir que o Supabase está inicializado
const ensureSupabaseInitialized = async () => {
  if (supabase) {
    return true;
  }
  
  // Tentar inicializar novamente
  await initializeSupabase();
  
  if (!supabase) {
    return false;
  }
  
  return true;
};

// Exportar cliente (pode ser null se não foi possível criar)
export { supabase };

// Função para buscar mensagens de uma conversa
export const getMessages = async (conversationId, provedorId) => {
  // Garantir que o Supabase está inicializado antes de usar
  const initialized = await ensureSupabaseInitialized();
  if (!initialized || !supabase) {
    return [];
  }
  try {
    const { data, error } = await supabase
      .from('mensagens')
      .select('*')
      .eq('conversation_id', conversationId)
      .eq('provedor_id', provedorId)
      .order('created_at', { ascending: true })
    
    if (error) throw error
    return data
  } catch (error) {
    return []
  }
}

// Função para buscar auditoria
export const getAuditLogs = async (provedorId, filters = {}) => {
  // Garantir que o Supabase está inicializado antes de usar
  const initialized = await ensureSupabaseInitialized();
  if (!initialized || !supabase) {
    return [];
  }
  try {
    // Converter provedorId para número se necessário (mesma lógica do CSAT)
    const provedorIdNum = typeof provedorId === 'string' ? parseInt(provedorId, 10) : provedorId;
    
    if (isNaN(provedorIdNum)) {
      return [];
    }
    
    let query = supabase
      .from('auditoria')
      .select('*')
      .eq('provedor_id', provedorIdNum)
      .order('ended_at', { ascending: false, nullsLast: true })
      .order('created_at', { ascending: false })
    
    // Aplicar filtros
    if (filters.conversation_closed) {
      query = query.in('action', ['conversation_closed_ai', 'conversation_closed_manual', 'conversation_closed_agent', 'conversation_closed_timeout'])
    }
    
    // Filtro por conversation_id (usado na página de detalhes)
    if (filters.conversation_id) {
      const convIdNum = typeof filters.conversation_id === 'string' ? parseInt(filters.conversation_id, 10) : filters.conversation_id;
      if (!isNaN(convIdNum)) {
        query = query.eq('conversation_id', convIdNum)
      }
    }
    
    if (filters.date_from) {
      query = query.gte('created_at', filters.date_from)
    }
    
    if (filters.date_to) {
      query = query.lte('created_at', filters.date_to)
    }
    
    const { data, error } = await query
    
    if (error) {
      return [];
    }
    
    return data || []
  } catch (error) {
    return []
  }
}

// Função para buscar CSAT feedback
export const getCSATFeedback = async (provedorId, filters = {}) => {
  // Garantir que o Supabase está inicializado antes de usar
  const initialized = await ensureSupabaseInitialized();
  if (!initialized || !supabase) {
    return [];
  }
  try {
    // Converter provedorId para número se necessário
    const provedorIdNum = typeof provedorId === 'string' ? parseInt(provedorId, 10) : provedorId;
    
    if (isNaN(provedorIdNum)) {
      return [];
    }
    
    // Buscar todos os campos necessários
    let query = supabase
      .from('csat_feedback')
      .select('*')
      .eq('provedor_id', provedorIdNum)
    
    // Aplicar filtros de data se disponíveis
    if (filters.date_from) {
      query = query.gte('feedback_sent_at', filters.date_from)
    }
    
    if (filters.date_to) {
      query = query.lte('feedback_sent_at', filters.date_to)
    }
    
    const { data, error } = await query
    
    if (error) {
      return [];
    }
    
    return data || []
  } catch (error) {
    return []
  }
}

// Função para calcular satisfação média (mantida para compatibilidade, mas não usada no dashboard principal)
export const getAverageSatisfaction = async (provedorId, filters = {}) => {
  try {
    const csatData = await getCSATFeedback(provedorId, filters)
    
    if (!csatData || csatData.length === 0) {
      return '0.0'
    }
    
    // Filtrar apenas itens com rating_value válido (número)
    const validRatings = csatData.filter(item => {
      const rating = item.rating_value;
      return rating !== null && 
             rating !== undefined && 
             !isNaN(Number(rating)) &&
             Number(rating) > 0;
    })
    
    if (validRatings.length === 0) {
      return '0.0'
    }
    
    // Converter rating_value para número e calcular média
    const totalRating = validRatings.reduce((sum, item) => {
      const rating = Number(item.rating_value);
      return sum + (isNaN(rating) ? 0 : rating);
    }, 0)
    
    const average = (totalRating / validRatings.length).toFixed(1)
    return average
  } catch (error) {
    return '0.0'
  }
}

// Função para calcular taxa de resolução
export const getResolutionRate = async (provedorId, filters = {}) => {
  try {
    const auditData = await getAuditLogs(provedorId, { ...filters, conversation_closed: true })
    
    if (auditData.length === 0) return 0
    
    // Contar conversas resolvidas (fechadas)
    const resolvedConversations = auditData.length
    
    // Aqui você pode adicionar lógica para contar total de conversas se necessário
    // Por enquanto, retornamos a porcentagem baseada nas conversas fechadas
    return resolvedConversations
  } catch (error) {
    return 0
  }
}

// Função para escutar mudanças em tempo real
export const subscribeToMessages = (conversationId, provedorId, callback) => {
  if (!supabase) {
    return null;
  }
  return supabase
    .channel('messages')
    .on('postgres_changes', {
      event: '*',
      schema: 'public',
      table: 'mensagens',
      filter: `conversation_id=eq.${conversationId}`
    }, callback)
    .subscribe()
}

// Função para escutar mudanças na auditoria
export const subscribeToAudit = (provedorId, callback) => {
  if (!supabase) {
    return null;
  }
  return supabase
    .channel('audit')
    .on('postgres_changes', {
      event: '*',
      schema: 'public',
      table: 'auditoria',
      filter: `provedor_id=eq.${provedorId}`
    }, callback)
    .subscribe()
}

// Função para escutar mudanças no CSAT
export const subscribeToCSAT = (provedorId, callback) => {
  if (!supabase) {
    return null;
  }
  return supabase
    .channel('csat')
    .on('postgres_changes', {
      event: '*',
      schema: 'public',
      table: 'csat_feedback',
      filter: `provedor_id=eq.${provedorId}`
    }, callback)
    .subscribe()
}