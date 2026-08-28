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
  // Mascarar credenciais na query: token, ticket, sig
  return url
    .replace(/([?&]token=)([^&]*)/gi, (match, prefix, token) => prefix + maskToken(token))
    .replace(/([?&]ticket=)([^&]*)/gi, (match, prefix, ticket) => prefix + maskToken(ticket))
    .replace(/([?&]sig=)([^&]*)/gi, (match, prefix, sig) => prefix + maskToken(sig));
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
 * Logger seguro que automaticamente mascara dados sensíveis.
 * Sem saída no console do navegador (no-op) — mantido apenas para
 * compatibilidade com chamadas existentes em outros arquivos.
 */
export const secureLogger = {
  log: () => {},
  error: () => {},
  warn: () => {},
};
