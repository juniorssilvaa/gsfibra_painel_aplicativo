/**
 * Utilitário para logging seguro que mascara informações sensíveis
 */

/**
 * Mascara um token para logging seguro
 * @param {string} token - Token a ser mascarado
 * @returns {string} Token mascarado
 */
export const maskToken = (token) => {
  if (!token || typeof token !== 'string') return '[NO_TOKEN]';
  if (token.length <= 8) return '[SHORT_TOKEN]';
  return `${token.substring(0, 4)}...${token.substring(token.length - 4)}`;
};

/**
 * Mascara token em URLs (especialmente WebSocket)
 * @param {string} url - URL que pode conter token
 * @returns {string} URL com token mascarado
 */
export const maskUrlToken = (url) => {
  if (!url || typeof url !== 'string') return url;
  // Mascarar token na query string: ?token=... ou &token=...
  return url.replace(/([?&]token=)([^&]*)/gi, (match, prefix, token) => {
    return prefix + maskToken(token);
  });
};

/**
 * Mascara dados sensíveis em objetos para logging
 * @param {any} data - Dados a serem mascarados
 * @returns {any} Dados com informações sensíveis mascaradas
 */
export const maskSensitiveData = (data) => {
  if (!data) return data;
  
  if (typeof data === 'string') {
    // Se for um token (formato típico de token Django)
    if (data.length > 20 && /^[a-f0-9]{40}$/.test(data)) {
      return maskToken(data);
    }
    return data;
  }
  
  if (typeof data === 'object') {
    const masked = { ...data };
    
    // Campos sensíveis para mascarar
    const sensitiveFields = ['token', 'password', 'secret', 'key', 'auth'];
    
    Object.keys(masked).forEach(key => {
      const lowerKey = key.toLowerCase();
      if (sensitiveFields.some(field => lowerKey.includes(field))) {
        masked[key] = maskToken(masked[key]);
      } else if (typeof masked[key] === 'object') {
        masked[key] = maskSensitiveData(masked[key]);
      }
    });
    
    return masked;
  }
  
  return data;
};

/**
 * Logger seguro que automaticamente mascara dados sensíveis
 */
export const secureLogger = {
  log: (message, data) => {
    if (data) {
      // Se for string e parecer URL, mascarar token
      if (typeof data === 'string' && (data.includes('ws://') || data.includes('wss://') || data.includes('?token='))) {
        console.log(message, maskUrlToken(data));
      } else {
        console.log(message, maskSensitiveData(data));
      }
    } else {
      // Se a própria mensagem contiver URL com token, mascarar
      if (typeof message === 'string' && (message.includes('ws://') || message.includes('wss://') || message.includes('?token='))) {
        console.log(maskUrlToken(message));
      } else {
        console.log(message);
      }
    }
  },
  
  error: (message, error) => {
    if (error) {
      // Se for string e parecer URL, mascarar token
      if (typeof error === 'string' && (error.includes('ws://') || error.includes('wss://') || error.includes('?token='))) {
        console.error(message, maskUrlToken(error));
      } else if (error?.message && (error.message.includes('ws://') || error.message.includes('wss://') || error.message.includes('?token='))) {
        console.error(message, { ...error, message: maskUrlToken(error.message) });
      } else if (error?.url && (error.url.includes('ws://') || error.url.includes('wss://') || error.url.includes('?token='))) {
        console.error(message, { ...error, url: maskUrlToken(error.url) });
      } else {
        console.error(message, maskSensitiveData(error));
      }
    } else {
      // Se a própria mensagem contiver URL com token, mascarar
      if (typeof message === 'string' && (message.includes('ws://') || message.includes('wss://') || message.includes('?token='))) {
        console.error(maskUrlToken(message));
      } else {
        console.error(message);
      }
    }
  },
  
  warn: (message, data) => {
    if (data) {
      // Se for string e parecer URL, mascarar token
      if (typeof data === 'string' && (data.includes('ws://') || data.includes('wss://') || data.includes('?token='))) {
        console.warn(message, maskUrlToken(data));
      } else {
        console.warn(message, maskSensitiveData(data));
      }
    } else {
      // Se a própria mensagem contiver URL com token, mascarar
      if (typeof message === 'string' && (message.includes('ws://') || message.includes('wss://') || message.includes('?token='))) {
        console.warn(maskUrlToken(message));
      } else {
        console.warn(message);
      }
    }
  }
};
