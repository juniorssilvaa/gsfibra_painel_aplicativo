import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { ShieldAlert, Copy, Check, RefreshCw, ExternalLink, CreditCard } from 'lucide-react';

const BlockedScreen = ({ onLogout }) => {
    const [loading, setLoading] = useState(true);
    const [statusData, setStatusData] = useState(null);
    const [copied, setCopied] = useState(false);
    const [checking, setChecking] = useState(false);
    const [unblocked, setUnblocked] = useState(false);

    const fetchStatus = async () => {
        setChecking(true);
        try {
            const response = await axios.get('/api/provedores/status_pagamento/');
            setStatusData(response.data);
            if (!response.data.blocked) {
                setUnblocked(true);
                setTimeout(() => window.location.reload(), 1800);
            }
        } catch (error) {
            console.error('Erro ao buscar status de pagamento:', error);
        } finally {
            setLoading(false);
            setChecking(false);
        }
    };

    useEffect(() => {
        fetchStatus();
    }, []);

    const copyToClipboard = (text) => {
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    if (loading) {
        return (
            <div className="min-h-screen bg-background flex items-center justify-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary" />
            </div>
        );
    }

    const { payment, pix, reason } = statusData || {};

    if (unblocked) {
        return (
            <div className="min-h-screen bg-background flex items-center justify-center p-4">
                <div className="max-w-lg w-full bg-card rounded-2xl shadow-lg border border-border p-8 text-center text-foreground">
                    <div className="text-primary text-2xl font-bold mb-2">Pagamento recebido!</div>
                    <p className="text-muted-foreground">
                        Seu acesso foi liberado. Redirecionando para o painel...
                    </p>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-dvh max-h-dvh overflow-y-auto overscroll-y-contain bg-background flex flex-col items-center px-3 py-3 sm:py-4 font-sans text-foreground">
            <div className="w-full max-w-2xl my-auto flex flex-col max-h-[min(100dvh-1rem,920px)] min-h-0 bg-card rounded-2xl sm:rounded-3xl shadow-2xl border border-border overflow-hidden">
                {/* Header Alerta — mais compacto em telas pequenas */}
                <div className="bg-gradient-to-r from-red-600 to-orange-600 px-4 py-5 sm:p-6 text-white relative shrink-0">
                    <div className="absolute top-0 right-0 p-4 opacity-10 pointer-events-none hidden sm:block">
                        <ShieldAlert size={100} />
                    </div>
                    <div className="relative z-10 flex items-start gap-3 sm:gap-4">
                        <div className="bg-white/20 p-2 sm:p-3 rounded-xl sm:rounded-2xl backdrop-blur-sm shrink-0">
                            <ShieldAlert className="w-7 h-7 sm:w-8 sm:h-8" />
                        </div>
                        <div className="min-w-0">
                            <h1 className="text-xl sm:text-3xl font-black tracking-tight leading-tight">Acesso Suspenso</h1>
                            <p className="text-white/90 text-sm sm:text-base font-medium mt-1">
                                Identificamos uma pendência financeira em sua assinatura.
                            </p>
                        </div>
                    </div>
                </div>

                {/* Mensagem importante sempre visível sem rolar até o fim */}
                <div className="px-4 py-3 bg-muted/70 border-b border-border text-sm sm:text-[15px] leading-snug text-center text-foreground shrink-0">
                    O seu acesso será restabelecido automaticamente em poucos segundos após a confirmação do pagamento.
                </div>

                <div className="p-4 sm:p-6 flex-1 min-h-0 overflow-y-auto bg-card">
                    <div className="grid md:grid-cols-2 gap-5 md:gap-6">
                        <div className="space-y-4 sm:space-y-5">
                            <div>
                                <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-2">Detalhes da Pendência</h3>
                                <div className="bg-muted/50 rounded-xl sm:rounded-2xl p-3 sm:p-4 border border-border">
                                    <div className="flex justify-between mb-1 gap-2">
                                        <span className="text-muted-foreground">Valor:</span>
                                        <span className="font-bold text-foreground text-base sm:text-lg tabular-nums">
                                            R$ {parseFloat(payment?.value || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                                        </span>
                                    </div>
                                    <div className="flex justify-between gap-2">
                                        <span className="text-muted-foreground">Vencimento:</span>
                                        <span className="font-medium text-destructive tabular-nums">
                                            {payment?.dueDate ? new Date(payment.dueDate + 'T12:00:00').toLocaleDateString('pt-BR') : 'N/A'}
                                        </span>
                                    </div>
                                </div>
                            </div>

                            {pix?.encodedImage ? (
                                <div className="flex flex-col items-center">
                                    <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-2 w-full">Pague via PIX</h3>
                                    {/* Fundo branco só no QR para leitura confiável nos bancos */}
                                    <div className="bg-white p-2 rounded-2xl border border-border shadow-sm">
                                        <img
                                            src={`data:image/png;base64,${pix.encodedImage}`}
                                            alt="QR Code Pix"
                                            className="w-36 h-36 sm:w-44 sm:h-44"
                                        />
                                    </div>
                                    <p className="text-xs text-muted-foreground mt-2 text-center max-w-[16rem]">
                                        Escaneie o QR Code com o app do seu banco
                                    </p>
                                </div>
                            ) : (
                                <div className="h-36 sm:h-44 flex items-center justify-center bg-muted/40 rounded-2xl border-2 border-dashed border-border">
                                    <p className="text-muted-foreground text-sm px-4 text-center">QR Code indisponível no momento</p>
                                </div>
                            )}
                        </div>

                        <div className="flex flex-col gap-5">
                            <div className="space-y-4">
                                {pix?.payload && (
                                    <div className="space-y-2">
                                        <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Pix Copia e Cola</h3>
                                        <button
                                            type="button"
                                            onClick={() => copyToClipboard(pix.payload)}
                                            className="w-full group relative flex items-center gap-2 p-3 sm:p-4 bg-muted/50 hover:bg-muted border border-border rounded-xl sm:rounded-2xl transition-all active:scale-[0.99] overflow-hidden"
                                        >
                                            <div className="flex-1 text-left truncate font-mono text-xs sm:text-sm text-foreground/90">
                                                {pix.payload}
                                            </div>
                                            <div className="bg-card border border-border p-2 rounded-lg shadow-sm shrink-0 group-hover:bg-primary group-hover:text-primary-foreground transition-colors">
                                                {copied ? <Check size={18} /> : <Copy size={18} />}
                                            </div>
                                        </button>
                                    </div>
                                )}

                                <div className="space-y-2">
                                    <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Outras Opções</h3>
                                    <a
                                        href={payment?.invoiceUrl}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="flex items-center justify-between p-3 sm:p-4 bg-muted/30 border border-border rounded-xl sm:rounded-2xl hover:border-primary transition-all group gap-2"
                                    >
                                        <div className="flex items-center gap-2 sm:gap-3 min-w-0">
                                            <div className="bg-primary/15 p-2 rounded-lg text-primary shrink-0">
                                                <CreditCard size={18} />
                                            </div>
                                            <span className="font-semibold text-foreground text-sm sm:text-base truncate">Ver Fatura Completa</span>
                                        </div>
                                        <ExternalLink size={18} className="text-muted-foreground group-hover:text-primary shrink-0" />
                                    </a>
                                </div>
                            </div>

                            <div className="space-y-2 pt-1 md:mt-auto">
                                <button
                                    type="button"
                                    onClick={fetchStatus}
                                    disabled={checking}
                                    className="w-full flex items-center justify-center gap-2 py-3 sm:py-3.5 bg-primary text-primary-foreground hover:bg-primary/90 rounded-xl sm:rounded-2xl font-bold text-sm sm:text-base transition-all disabled:opacity-50"
                                >
                                    <RefreshCw size={18} className={checking ? 'animate-spin' : ''} />
                                    {checking ? 'Verificando...' : 'Já realizei o pagamento'}
                                </button>
                                <button
                                    type="button"
                                    onClick={onLogout}
                                    className="w-full py-2.5 text-muted-foreground hover:text-destructive font-medium text-sm transition-colors"
                                >
                                    Sair da conta
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default BlockedScreen;
