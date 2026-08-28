import React from 'react';
import { Wifi, Battery, Signal, Zap } from 'lucide-react';
import { motion } from 'framer-motion';

export default function AppPreview({
    theme = 'dark',
    providerName = 'JOCA NET',
    activeContract = true
}) {
    const isDark = theme === 'dark';

    return (
        <div className="flex flex-col items-center justify-center p-4">
            <div className="text-sm font-medium text-muted-foreground mb-4 uppercase tracking-wider">
                Pré-visualização do App
            </div>

            {/* Mobile Frame */}
            <div className="relative w-[300px] h-[600px] bg-black rounded-[3rem] border-[8px] border-zinc-800 shadow-2xl overflow-hidden ring-4 ring-zinc-900">

                {/* Notch */}
                <div className="absolute top-0 left-1/2 -translate-x-1/2 w-32 h-6 bg-zinc-800 rounded-b-2xl z-20 flex items-center justify-center">
                    <div className="w-10 h-1 bg-zinc-900 rounded-full" />
                </div>

                {/* Status Bar */}
                <div className={`absolute top-0 left-0 right-0 h-12 flex items-center justify-between px-8 z-10 ${isDark ? 'text-white' : 'text-zinc-900'}`}>
                    <div className="text-xs font-bold">9:41</div>
                    <div className="flex items-center gap-1.5 font-bold">
                        <Signal className="w-3.5 h-3.5" />
                        <Wifi className="w-3.5 h-3.5" />
                        <Battery className="w-3.5 h-3.5 rotate-90" />
                    </div>
                </div>

                {/* App Content */}
                <div className={`w-full h-full flex flex-col transition-colors duration-500 ${isDark ? 'bg-zinc-950' : 'bg-zinc-50'}`}>

                    {/* Background Gradient */}
                    <div className={`absolute inset-0 opacity-20 pointer-events-none ${isDark ? 'bg-gradient-to-b from-blue-600/30 to-transparent' : 'bg-gradient-to-b from-blue-400/20 to-transparent'}`} />

                    {/* Body Content */}
                    <div className="flex-1 pt-16 px-6 relative z-0">

                        {/* Greeting */}
                        <motion.div
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="mb-8"
                        >
                            <h2 className={`text-2xl font-bold ${isDark ? 'text-white' : 'text-zinc-900'}`}>
                                Acesse sua conta
                            </h2>
                            <p className="text-sm text-zinc-500 mt-1">
                                Bem-vindo ao app da {providerName}
                            </p>
                        </motion.div>

                        {/* Notification Simulation (Glassmorphism) */}
                        <motion.div
                            initial={{ opacity: 0, scale: 0.95 }}
                            animate={{ opacity: 1, scale: 1 }}
                            transition={{ delay: 0.2 }}
                            className={`p-4 rounded-2xl border backdrop-blur-md shadow-lg ${isDark
                                    ? 'bg-zinc-900/40 border-zinc-800/50'
                                    : 'bg-white/40 border-zinc-200/50'
                                }`}
                        >
                            <div className="flex items-center gap-3 mb-3">
                                <div className="w-8 h-8 rounded-lg bg-[#1A237E] flex items-center justify-center">
                                    <Zap className="w-4 h-4 text-white fill-white" />
                                </div>
                                <div>
                                    <div className={`text-xs font-bold uppercase tracking-tighter ${isDark ? 'text-white' : 'text-zinc-900'}`}>
                                        {providerName}
                                    </div>
                                    <div className="text-[10px] text-zinc-500">AGORA</div>
                                </div>
                            </div>
                            <div className={`text-sm font-bold mb-1 ${isDark ? 'text-zinc-100' : 'text-zinc-900'}`}>
                                Sua fatura vence hoje!
                            </div>
                            <div className="text-xs text-zinc-500 leading-relaxed">
                                Evite multas e juros. Acesse o app para gerar seu código PIX ou boleto.
                            </div>
                        </motion.div>

                        {/* Simulated Card */}
                        <div className={`mt-6 p-5 rounded-2xl border ${isDark
                                ? 'bg-zinc-900/80 border-zinc-800'
                                : 'bg-white border-zinc-100 shadow-sm'
                            }`}>
                            <div className="flex items-center justify-between mb-4">
                                <div className="text-[10px] text-zinc-500 font-bold uppercase tracking-widest">Contrato</div>
                                <div className="flex items-center gap-1.5">
                                    <div className="w-1.5 h-1.5 rounded-full bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.5)]" />
                                    <span className="text-[10px] text-green-500 font-bold">ATIVO</span>
                                </div>
                            </div>
                            <div className={`text-lg font-bold mb-1 ${isDark ? 'text-white' : 'text-zinc-900'}`}>
                                Premium Fiber 500M
                            </div>
                            <div className="text-xs text-zinc-500">Rua das Flores, 123 - Centro</div>
                        </div>

                        {/* Simulated Button */}
                        <div className="mt-8">
                            <div className="w-full h-12 rounded-xl bg-[#1A237E] flex items-center justify-center font-bold text-white shadow-lg shadow-blue-900/20 active:scale-95 transition-transform">
                                Pagar Fatura
                            </div>
                        </div>

                    </div>

                    {/* Home Indicator */}
                    <div className="h-8 flex items-center justify-center">
                        <div className={`w-32 h-1.5 rounded-full ${isDark ? 'bg-zinc-800' : 'bg-zinc-200'}`} />
                    </div>

                </div>
            </div>
        </div>
    );
}
