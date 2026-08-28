import React, { useState, useEffect, useRef } from 'react';
import { Download, FileText, File, Image, Video, Music } from 'lucide-react';
import { buildMediaUrl } from '../config/environment';

// pdfjs-dist será carregado dinamicamente no useEffect para compatibilidade com Vite

const FilePreview = ({ file, isCustomer = false, className = '', content = null }) => {
  const {
    url,
    name,
    size,
    type,
    pages,
    jpegThumbnail
  } = file;
  
  // Verificar se há URL da Uazapi nos additional_attributes (prioridade sobre URL local)
  const uazapiUrl = file.additional_attributes?.file_url || file.uazapi_url;

  const [thumbnail, setThumbnail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const thumbnailRef = useRef(null);

  // Verificar se é PDF
  const isPdf = type === 'application/pdf' || name?.toLowerCase().endsWith('.pdf');
  
  // Verificar se há thumbnail do backend (vem do WhatsApp via Uazapi)
  // Aceita tanto jpegThumbnail quanto pdf_thumbnail (retrocompatibilidade)
  const backendThumbnail = jpegThumbnail || file.pdf_thumbnail || file.additional_attributes?.pdf_thumbnail;

  // Construir URL correta para download/visualização
  const getFileUrl = () => {
    // Priorizar URL da Uazapi (original) sobre URL local
    if (uazapiUrl && (uazapiUrl.startsWith('http://') || uazapiUrl.startsWith('https://'))) {
      return uazapiUrl.endsWith('/') ? uazapiUrl.slice(0, -1) : uazapiUrl;
    }
    
    // Fallback: usar URL passada como prop
    if (!url) return null;
    
    // Se já é URL completa, remover barra final e retornar
    if (url.startsWith('http://') || url.startsWith('https://')) {
      return url.endsWith('/') ? url.slice(0, -1) : url;
    }
    
    // Construir URL usando buildMediaUrl (URL local)
    let mediaUrl = buildMediaUrl(url);
    
    // Remover barra final se houver (importante para evitar 404)
    if (mediaUrl && mediaUrl.endsWith('/')) {
      mediaUrl = mediaUrl.slice(0, -1);
    }
    
    return mediaUrl;
  };

  // Gerar thumbnail do PDF
  useEffect(() => {
    if (!isPdf || !url) {
      setLoading(false);
      return;
    }

    let cancelled = false;

    // Função para usar thumbnail da Uazapi (WhatsApp)
    const useThumbnailFromUazapi = () => {
      if (backendThumbnail) {
        try {
          // O thumbnail vem em base64 (sem prefixo), adicionar prefixo data URL
          let thumbnailDataUrl = backendThumbnail.trim();
          
          // Se já tem prefixo data:, usar como está
          if (thumbnailDataUrl.startsWith('data:')) {
            if (!cancelled) {
              setThumbnail(thumbnailDataUrl);
              setLoading(false);
            }
            return true;
          }
          
          // Se não tem prefixo, adicionar
          thumbnailDataUrl = `data:image/jpeg;base64,${thumbnailDataUrl}`;
          
          if (!cancelled) {
            setThumbnail(thumbnailDataUrl);
            setLoading(false);
          }
          return true;
        } catch (err) {
          console.error('FilePreview: Erro ao processar JPEGThumbnail da Uazapi:', err);
        }
      }
      return false;
    };

    // Função para gerar thumbnail com pdf.js (fallback)
    const generateThumbnailWithPdfJs = async () => {
      try {
        setLoading(true);
        setError(false);

        const fileUrl = getFileUrl();
        if (!fileUrl) {
          setLoading(false);
          return;
        }

        // Carregar pdfjs-dist dinamicamente
        const pdfjsModule = await import('pdfjs-dist');
        const pdfjsLib = pdfjsModule.default || pdfjsModule;
        
        // Configurar worker se ainda não estiver configurado
        if (pdfjsLib.GlobalWorkerOptions && !pdfjsLib.GlobalWorkerOptions.workerSrc) {
          pdfjsLib.GlobalWorkerOptions.workerSrc = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjsLib.version || '4.0.379'}/pdf.worker.min.js`;
        }

        const getDocument = pdfjsLib.getDocument;
        
        if (!getDocument) {
          throw new Error('getDocument não está disponível');
        }

        // Carregar PDF - usar modo cors para evitar problemas de CORS
        const loadingTask = getDocument({
          url: fileUrl,
          withCredentials: false,
          httpHeaders: {},
          verbosity: 0 // Reduzir logs
        });

        const pdf = await loadingTask.promise;
        
        if (cancelled) return;

        // Obter primeira página
        const page = await pdf.getPage(1);
        
        if (cancelled) return;

        // Configurar viewport com scale reduzido para performance
        const viewport = page.getViewport({ scale: 0.5 });
        
        // Criar canvas virtual
        const canvas = document.createElement('canvas');
        const context = canvas.getContext('2d');
        canvas.width = viewport.width;
        canvas.height = viewport.height;

        // Renderizar página no canvas
        await page.render({
          canvasContext: context,
          viewport: viewport
        }).promise;

        if (cancelled) return;

        // Converter para data URL (JPEG com qualidade reduzida)
        const thumbnailDataUrl = canvas.toDataURL('image/jpeg', 0.7);
        if (!cancelled) {
          setThumbnail(thumbnailDataUrl);
          setLoading(false);
        }
      } catch (err) {
        console.error('FilePreview: Erro ao gerar thumbnail do PDF:', err);
        setError(true);
        setLoading(false);
      }
    };

    // 1) Tenta usar a thumbnail que veio da Uazapi (WhatsApp)
    const alreadyHandled = useThumbnailFromUazapi();
    if (alreadyHandled) {
      return () => {
        cancelled = true;
      };
    }

    // 2) Se não tiver jpegThumbnail, cai no fallback com pdf.js
    generateThumbnailWithPdfJs();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, isPdf, backendThumbnail]);

  // Formatar tamanho do arquivo
  const formatFileSize = (bytes) => {
    if (!bytes) return '';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  // Detectar se é comprovante PIX
  const isPixReceipt = () => {
    if (!content) return false;
    const contentLower = content.toLowerCase();
    return contentLower.includes('comprovante') || 
           contentLower.includes('pix') || 
           contentLower.includes('pagamento');
  };

  // Extrair informações do comprovante do conteúdo
  const extractReceiptInfo = () => {
    if (!content || !isPixReceipt()) return null;
    
    // Tentar extrair data/hora do conteúdo
    const dateMatch = content.match(/(\d{2}\/\d{2}\/\d{4})\s*-\s*(\d{2}:\d{2}:\d{2})/);
    const dateTime = dateMatch ? `${dateMatch[1]} - ${dateMatch[2]}` : null;
    
    // Tentar extrair título
    const titleMatch = content.match(/Comprovante\s+(?:do\s+)?(?:Pix|PIX|Pagamento)/i);
    const title = titleMatch ? titleMatch[0] : 'Comprovante do Pix';
    
    return {
      title,
      dateTime
    };
  };

  // Detectar tipo de arquivo e retornar configuração
  const getFileConfig = (mimeType, fileName) => {
    const ext = fileName?.split('.').pop()?.toLowerCase() || '';
    
    // PDF
    if (mimeType === 'application/pdf' || ext === 'pdf') {
      return {
        icon: FileText,
        color: '#E32636', // Vermelho para PDF
        label: 'PDF',
        bgColor: isCustomer ? '#1F2937' : '#064E3B' // Verde escuro WhatsApp
      };
    }
    
    // Imagens
    if (mimeType?.startsWith('image/') || ['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext)) {
      return {
        icon: Image,
        color: '#10B981',
        label: 'Imagem',
        bgColor: isCustomer ? '#1F2937' : '#064E3B'
      };
    }
    
    // Vídeos
    if (mimeType?.startsWith('video/') || ['mp4', 'avi', 'mov', 'wmv'].includes(ext)) {
      return {
        icon: Video,
        color: '#3B82F6',
        label: 'Vídeo',
        bgColor: isCustomer ? '#1F2937' : '#064E3B'
      };
    }
    
    // Áudios
    if (mimeType?.startsWith('audio/') || ['mp3', 'wav', 'ogg', 'm4a'].includes(ext)) {
      return {
        icon: Music,
        color: '#8B5CF6',
        label: 'Áudio',
        bgColor: isCustomer ? '#1F2937' : '#064E3B'
      };
    }
    
    // Word
    if (mimeType?.includes('wordprocessingml') || ext === 'doc' || ext === 'docx') {
      return {
        icon: FileText,
        color: '#2563EB',
        label: 'Word',
        bgColor: isCustomer ? '#1F2937' : '#064E3B'
      };
    }
    
    // Excel
    if (mimeType?.includes('spreadsheetml') || ext === 'xls' || ext === 'xlsx') {
      return {
        icon: FileText,
        color: '#059669',
        label: 'Excel',
        bgColor: isCustomer ? '#1F2937' : '#064E3B'
      };
    }
    
    // Genérico
    return {
      icon: File,
      color: '#6B7280',
      label: 'Arquivo',
      bgColor: isCustomer ? '#1F2937' : '#064E3B'
    };
  };

  const fileConfig = getFileConfig(type, name);
  const IconComponent = fileConfig.icon;
  const displayName = name || 'Documento';
  const displaySize = formatFileSize(size);
  const fileTypeLabel = fileConfig.label;
  const receiptInfo = extractReceiptInfo();
  const isReceipt = isPixReceipt() && isPdf;

  const fileUrl = getFileUrl();

  // Construir string de detalhes
  let detailsText = '';
  if (pages) {
    detailsText = `${pages} páginas • `;
  }
  detailsText += `${fileTypeLabel} • ${displaySize}`;

  const handleDownload = async (e) => {
    e.stopPropagation();
    e.preventDefault();
    
    if (!fileUrl) {
      console.error('URL do arquivo não disponível');
      return;
    }

    // Construir URL completa
    let downloadUrl = getFileUrl();
    if (!downloadUrl) {
      console.error('Não foi possível construir URL do arquivo');
      return;
    }

    // Remover barra final se houver
    downloadUrl = downloadUrl.endsWith('/') ? downloadUrl.slice(0, -1) : downloadUrl;

    try {
      // Obter token de autenticação
      const token = localStorage.getItem('token');
      
      // Tentar fazer download com fetch e autenticação
      const response = await fetch(downloadUrl, {
        method: 'GET',
        headers: {
          'Authorization': `Token ${token}`,
          'Accept': '*/*'
        },
        credentials: 'include'
      });

      if (response.ok) {
        // Obter blob do arquivo
        const blob = await response.blob();
        
        if (blob && blob.size > 0) {
          // Criar URL temporária do blob
          const blobUrl = window.URL.createObjectURL(blob);
          
          // Criar link temporário para download
          const link = document.createElement('a');
          link.href = blobUrl;
          link.download = displayName;
          link.style.display = 'none';
          document.body.appendChild(link);
          link.click();
          
          // Limpar após um pequeno delay
          setTimeout(() => {
            document.body.removeChild(link);
            window.URL.revokeObjectURL(blobUrl);
          }, 100);
          return;
        }
      }
    } catch (error) {
      console.warn('Erro ao fazer download via fetch:', error);
    }

    // Fallback: abrir em nova aba (comportamento padrão do navegador)
    window.open(downloadUrl, '_blank');
  };

  // Componente de placeholder/shimmer para loading
  const ShimmerPlaceholder = () => (
    <div
      style={{
        width: '100%',
        height: '200px',
        backgroundColor: '#E5E7EB',
        borderRadius: '8px',
        position: 'relative',
        overflow: 'hidden'
      }}
    >
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: '-100%',
          width: '100%',
          height: '100%',
          background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent)',
          animation: 'shimmer 1.5s infinite'
        }}
      />
      <style>{`
        @keyframes shimmer {
          0% { left: -100%; }
          100% { left: 100%; }
        }
      `}</style>
    </div>
  );

  // Layout estilo WhatsApp para PDFs comprovantes (com seção branca e thumbnail se disponível)
  if (isReceipt && receiptInfo) {
    return (
      <div 
        className={`file-preview-container ${className}`}
        style={{
          maxWidth: '320px',
          borderRadius: '8px',
          overflow: 'hidden',
          cursor: 'pointer',
          boxShadow: '0 1px 2px rgba(0,0,0,0.1)'
        }}
      >
        {/* Preview da primeira página do PDF se disponível */}
        {loading && !thumbnail && (
          <div style={{ padding: '8px', backgroundColor: '#FFFFFF' }}>
            <ShimmerPlaceholder />
          </div>
        )}
        
        {thumbnail && !loading && (
          <div style={{ padding: '8px', backgroundColor: '#FFFFFF' }}>
            <img
              ref={thumbnailRef}
              src={thumbnail}
              alt="Preview do comprovante"
              style={{
                width: '100%',
                height: 'auto',
                maxHeight: '200px',
                objectFit: 'contain',
                borderRadius: '4px',
                display: 'block'
              }}
              onError={() => {
                setError(true);
                setThumbnail(null);
              }}
            />
          </div>
        )}

        {/* Seção superior branca (título do comprovante) */}
        <div
          style={{
            backgroundColor: '#FFFFFF',
            padding: '12px',
            borderTopLeftRadius: (thumbnail || loading) ? '0' : '8px',
            borderTopRightRadius: (thumbnail || loading) ? '0' : '8px'
          }}
        >
          <div
            style={{
              fontSize: '14px',
              fontWeight: 600,
              color: '#1F2937',
              marginBottom: receiptInfo.dateTime ? '4px' : '0'
            }}
          >
            {receiptInfo.title}
          </div>
          {receiptInfo.dateTime && (
            <div
              style={{
                fontSize: '12px',
                color: '#6B7280',
                marginTop: '4px'
              }}
            >
              {receiptInfo.dateTime}
            </div>
          )}
        </div>

        {/* Seção inferior com informações do arquivo */}
        <div
          style={{
            backgroundColor: fileConfig.bgColor,
            padding: '12px',
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            transition: 'background-color 0.2s'
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = isCustomer ? '#374151' : '#065F46';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = fileConfig.bgColor;
          }}
        >
          {/* Ícone PDF vermelho (fallback se não tiver thumbnail) */}
          {(!thumbnail || error) && (
            <div
              style={{
                width: '40px',
                height: '40px',
                backgroundColor: fileConfig.color,
                borderRadius: '4px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0
              }}
            >
              <IconComponent className="w-5 h-5 text-white" />
            </div>
          )}

          {/* Informações do arquivo */}
          <div style={{ flex: 1, minWidth: 0 }}>
            <div
              style={{
                color: 'white',
                fontSize: '14px',
                fontWeight: 500,
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                marginBottom: '2px'
              }}
              title={displayName}
            >
              {displayName}
            </div>
            <div
              style={{
                color: 'rgba(255, 255, 255, 0.7)',
                fontSize: '12px'
              }}
            >
              {detailsText}
            </div>
          </div>

          {/* Botão de download */}
          <button
            onClick={handleDownload}
            style={{
              width: '32px',
              height: '32px',
              backgroundColor: 'rgba(255, 255, 255, 0.1)',
              border: 'none',
              borderRadius: '50%',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'background-color 0.2s',
              flexShrink: 0
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.2)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.1)';
            }}
            title="Baixar arquivo"
          >
            <Download className="w-4 h-4 text-white" />
          </button>
        </div>
      </div>
    );
  }

  // Layout estilo WhatsApp para PDFs normais (com thumbnail se disponível)
  if (isPdf) {
    return (
      <div 
        className={`file-preview-container ${className}`}
        style={{
          maxWidth: '320px',
          borderRadius: '8px',
          overflow: 'hidden',
          cursor: 'pointer',
          boxShadow: '0 1px 2px rgba(0,0,0,0.1)',
          backgroundColor: fileConfig.bgColor
        }}
      >
        {/* Preview da primeira página do PDF */}
        {loading && !thumbnail && (
          <div style={{ padding: '8px' }}>
            <ShimmerPlaceholder />
          </div>
        )}
        
        {thumbnail && !loading && (
          <div style={{ padding: '8px' }}>
            <img
              ref={thumbnailRef}
              src={thumbnail}
              alt="Preview do PDF"
              style={{
                width: '100%',
                height: 'auto',
                maxHeight: '200px',
                objectFit: 'contain',
                borderRadius: '4px',
                backgroundColor: '#FFFFFF',
                display: 'block'
              }}
              onError={() => {
                setError(true);
                setThumbnail(null);
              }}
            />
          </div>
        )}

        {/* Seção inferior verde escuro (informações do arquivo) */}
        <div
          style={{
            backgroundColor: fileConfig.bgColor,
            padding: '12px',
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            borderBottomLeftRadius: '8px',
            borderBottomRightRadius: '8px',
            transition: 'background-color 0.2s'
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = isCustomer ? '#374151' : '#065F46';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = fileConfig.bgColor;
          }}
        >
          {/* Ícone PDF vermelho */}
          <div
            style={{
              width: '40px',
              height: '40px',
              backgroundColor: fileConfig.color,
              borderRadius: '4px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0
            }}
          >
            <IconComponent className="w-5 h-5 text-white" />
          </div>

          {/* Informações do arquivo */}
          <div style={{ flex: 1, minWidth: 0 }}>
            <div
              style={{
                color: 'white',
                fontSize: '14px',
                fontWeight: 500,
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                marginBottom: '2px'
              }}
              title={displayName}
            >
              {displayName}
            </div>
            <div
              style={{
                color: 'rgba(255, 255, 255, 0.7)',
                fontSize: '12px'
              }}
            >
              {detailsText}
            </div>
          </div>

          {/* Botão de download */}
          <button
            onClick={handleDownload}
            style={{
              width: '32px',
              height: '32px',
              backgroundColor: 'rgba(255, 255, 255, 0.1)',
              border: 'none',
              borderRadius: '50%',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'background-color 0.2s',
              flexShrink: 0
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.2)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.1)';
            }}
            title="Baixar arquivo"
          >
            <Download className="w-4 h-4 text-white" />
          </button>
        </div>
      </div>
    );
  }

  // Layout padrão para outros tipos de arquivo
  return (
    <div 
      className={`file-preview-container ${className}`}
      style={{
        backgroundColor: fileConfig.bgColor,
        borderRadius: '8px',
        padding: '12px',
        maxWidth: '320px',
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
        cursor: 'pointer',
        transition: 'background-color 0.2s',
        boxShadow: '0 1px 2px rgba(0,0,0,0.1)'
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.backgroundColor = isCustomer ? '#374151' : '#065F46';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.backgroundColor = fileConfig.bgColor;
      }}
    >
      {/* Ícone do arquivo */}
      <div
        style={{
          width: '40px',
          height: '40px',
          backgroundColor: fileConfig.color,
          borderRadius: '4px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0
        }}
      >
        <IconComponent className="w-5 h-5 text-white" />
      </div>

      {/* Informações do arquivo */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            color: 'white',
            fontSize: '14px',
            fontWeight: 500,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            marginBottom: '2px'
          }}
          title={displayName}
        >
          {displayName}
        </div>
        <div
          style={{
            color: 'rgba(255, 255, 255, 0.7)',
            fontSize: '12px'
          }}
        >
          {detailsText}
        </div>
      </div>

      {/* Botão de download */}
      <button
        onClick={handleDownload}
        style={{
          width: '32px',
          height: '32px',
          backgroundColor: 'rgba(255, 255, 255, 0.1)',
          border: 'none',
          borderRadius: '50%',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          transition: 'background-color 0.2s',
          flexShrink: 0
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.2)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.1)';
        }}
        title="Baixar arquivo"
      >
        <Download className="w-4 h-4 text-white" />
      </button>
    </div>
  );
};

export default FilePreview;
