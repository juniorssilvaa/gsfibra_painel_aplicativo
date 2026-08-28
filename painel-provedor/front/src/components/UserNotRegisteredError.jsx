import React from 'react';

const UserNotRegisteredError = () => {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-[#1a1f2e]">
      <div className="max-w-md w-full p-8 bg-[#242b3d] rounded-lg shadow-lg border border-[#2d3548]">
        <div className="text-center">
          <div className="inline-flex items-center justify-center w-16 h-16 mb-6 rounded-full bg-orange-500/20 border border-orange-500/30">
            <svg className="w-8 h-8 text-orange-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h1 className="text-3xl font-bold text-white mb-4">Acesso Restrito</h1>
          <p className="text-[#6b7280] mb-8">
            Você não está registrado para usar esta aplicação. Por favor, entre em contato com o administrador do sistema para solicitar acesso.
          </p>
          <div className="p-4 bg-[#1a1f2e] rounded-md text-sm text-[#9ca3af] border border-[#2d3548]">
            <p className="mb-2">Se você acredita que isso é um erro, você pode:</p>
            <ul className="list-disc list-inside space-y-1 text-left">
              <li>Verificar se está logado com a conta correta</li>
              <li>Entrar em contato com o administrador do sistema para solicitar acesso</li>
              <li>Tentar fazer logout e entrar novamente</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
};

export default UserNotRegisteredError;

