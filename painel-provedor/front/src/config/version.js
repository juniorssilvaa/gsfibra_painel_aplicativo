/**
 * Configuração de versão do aplicativo
 */
export const APP_VERSION = '2.68.0';

/**
 * Informações da versão
 */
export const VERSION_INFO = {
  version: APP_VERSION,
  buildDate: new Date().toISOString(),
  environment: import.meta.env.MODE || 'development'
};
