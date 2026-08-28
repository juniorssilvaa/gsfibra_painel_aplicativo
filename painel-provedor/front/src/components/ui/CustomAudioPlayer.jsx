import React, { useRef, useState, useEffect, useCallback, useMemo } from 'react';
import { Play, Pause, Volume2, Download, FastForward } from 'lucide-react';
import { getApiBaseUrl } from '../../utils/apiBaseUrl';

function isValidDuration(value) {
  return typeof value === 'number' && Number.isFinite(value) && value > 0;
}

function readDurationFromElement(audio) {
  if (!audio) return 0;
  if (isValidDuration(audio.duration)) return audio.duration;
  if (audio.seekable?.length > 0) {
    const end = audio.seekable.end(audio.seekable.length - 1);
    if (isValidDuration(end)) return end;
  }
  return 0;
}

/** WebM/OGG sem metadados: força o navegador a calcular a duração real. */
function probeDurationViaSeek(audio) {
  return new Promise((resolve) => {
    if (!audio) {
      resolve(0);
      return;
    }

    const existing = readDurationFromElement(audio);
    if (isValidDuration(existing)) {
      resolve(existing);
      return;
    }

    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      audio.removeEventListener('durationchange', onDurationChange);
      audio.removeEventListener('seeked', onSeeked);
      audio.removeEventListener('error', onError);
      try {
        if (audio.currentTime > 0.05) audio.currentTime = 0;
      } catch (_) {
        /* ignore */
      }
      resolve(isValidDuration(value) ? value : readDurationFromElement(audio));
    };

    const onDurationChange = () => {
      const d = readDurationFromElement(audio);
      if (isValidDuration(d)) finish(d);
    };

    const onSeeked = () => {
      finish(readDurationFromElement(audio));
    };

    const onError = () => finish(0);

    audio.addEventListener('durationchange', onDurationChange);
    audio.addEventListener('seeked', onSeeked, { once: true });
    audio.addEventListener('error', onError, { once: true });

    try {
      audio.currentTime = 1e12;
    } catch (_) {
      finish(0);
    }

    window.setTimeout(() => finish(readDurationFromElement(audio)), 2500);
  });
}

export default function CustomAudioPlayer({ src, isCustomer, conversationId }) {
  const audioRef = useRef(null);
  const containerRef = useRef(null);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [progress, setProgress] = useState(0);
  const [duration, setDuration] = useState(0);
  const [speed, setSpeed] = useState(1);
  const [error, setError] = useState(null);
  const [isLoaded, setIsLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [blobUrl, setBlobUrl] = useState(null);
  // Lazy: não dispara dezenas de GET ao abrir conversa com muitos áudios
  const [shouldLoad, setShouldLoad] = useState(false);
  const pendingPlayRef = useRef(false);

  const normalizeUrl = useCallback((url) => {
    if (!url) return null;
    if (url.startsWith('http://') || url.startsWith('https://') || url.startsWith('blob:')) {
      return url;
    }
    if (url.startsWith('/')) {
      return `${window.location.origin}${url}`;
    }
    return `${window.location.origin}/${url}`;
  }, []);

  const resolvedSrc = useMemo(() => {
    if (!src) return null;
    const isAbsoluteHttp = src.startsWith('http://') || src.startsWith('https://');
    const isLocalHost =
      src.includes('localhost') ||
      src.includes('127.0.0.1') ||
      src.includes('192.168.') ||
      src.includes('10.0.');
    // URLs do Superadmin (app mobile) e Meta precisam de proxy (CORS + http local).
    if (
      isAbsoluteHttp &&
      !src.startsWith('data:') &&
      !src.startsWith('blob:') &&
      (
        src.includes('lookaside.fbsbx.com') ||
        src.includes('facebook.com') ||
        src.includes('/v1/support/files/') ||
        (!isLocalHost && !src.includes('/api/media/') && !src.includes(window.location.hostname))
      )
    ) {
      const apiUrl = getApiBaseUrl();
      let proxyUrl = `${apiUrl}/api/media/proxy/?url=${encodeURIComponent(src)}`;
      if (conversationId) {
        proxyUrl += `&conversation_id=${conversationId}`;
      }
      return proxyUrl;
    }
    return normalizeUrl(src);
  }, [src, conversationId, normalizeUrl]);

  const requiresBlobFetch = Boolean(
    shouldLoad && resolvedSrc?.includes('/api/media/proxy/')
  );
  const finalSrc = shouldLoad
    ? (blobUrl || (requiresBlobFetch ? null : resolvedSrc))
    : null;

  useEffect(() => {
    const el = containerRef.current;
    if (!el || !resolvedSrc) return undefined;
    if (typeof IntersectionObserver === 'undefined') {
      setShouldLoad(true);
      return undefined;
    }
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          setShouldLoad(true);
          io.disconnect();
        }
      },
      { rootMargin: '120px' }
    );
    io.observe(el);
    return () => io.disconnect();
  }, [resolvedSrc]);

  const needsCrossOrigin = Boolean(
    finalSrc &&
      finalSrc.startsWith('http') &&
      !finalSrc.startsWith(window.location.origin)
  );

  const syncDuration = useCallback(async () => {
    const audio = audioRef.current;
    if (!audio) return;

    let d = readDurationFromElement(audio);
    if (!isValidDuration(d)) {
      d = await probeDurationViaSeek(audio);
    }
    if (isValidDuration(d)) {
      setDuration(d);
    }
    setIsLoaded(true);
    setLoading(false);
    setError(null);
  }, []);

  const downloadExternalAudio = useCallback(async (url) => {
    try {
      if (!url) {
        setError('URL de áudio inválida');
        setLoading(false);
        return;
      }

      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const headers = { Accept: 'audio/*,video/*,*/*' };
      if (token) headers.Authorization = `Token ${token}`;

      const response = await fetch(url, {
        method: 'GET',
        credentials: 'include',
        headers,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const blob = await response.blob();
      const newBlobUrl = URL.createObjectURL(blob);
      setBlobUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return newBlobUrl;
      });
      setError(null);
    } catch (err) {
      setError(`Erro ao baixar áudio: ${err.message}`);
      setLoading(false);
      setIsLoaded(false);
    }
  }, []);

  useEffect(() => {
    if (!shouldLoad) return;
    setLoading(true);
    setIsLoaded(false);
    setError(null);
    setProgress(0);
    setDuration(0);
    setPlaying(false);
    setBlobUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });

    if (!resolvedSrc) {
      setLoading(false);
      return;
    }

    if (requiresBlobFetch) {
      downloadExternalAudio(resolvedSrc);
    } else {
      setLoading(false);
    }
  }, [shouldLoad, resolvedSrc, requiresBlobFetch, downloadExternalAudio]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || !finalSrc) return;

    let cancelled = false;

    const onTimeUpdate = () => {
      if (cancelled || !audio) return;
      setProgress(audio.currentTime || 0);
      const d = readDurationFromElement(audio);
      if (isValidDuration(d)) {
        setDuration((prev) => (prev !== d ? d : prev));
      }
    };

    const onMeta = () => {
      if (!cancelled) syncDuration();
    };

    audio.addEventListener('timeupdate', onTimeUpdate);
    audio.addEventListener('loadedmetadata', onMeta);
    audio.addEventListener('durationchange', onMeta);
    audio.addEventListener('canplay', onMeta);

    audio.load();
    onMeta();

    return () => {
      cancelled = true;
      audio.removeEventListener('timeupdate', onTimeUpdate);
      audio.removeEventListener('loadedmetadata', onMeta);
      audio.removeEventListener('durationchange', onMeta);
      audio.removeEventListener('canplay', onMeta);
    };
  }, [finalSrc, syncDuration]);

  useEffect(() => {
    return () => {
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
  }, [blobUrl]);

  const togglePlay = async () => {
    if (!shouldLoad) {
      pendingPlayRef.current = true;
      setShouldLoad(true);
      setLoading(true);
      return;
    }
    const audio = audioRef.current;
    if (!audio) {
      setError('Elemento de áudio não encontrado');
      return;
    }
    if (loading) {
      setError('Aguarde o áudio carregar...');
      return;
    }

    try {
      if (!isValidDuration(duration)) {
        await syncDuration();
      }
      if (playing) {
        audio.pause();
      } else {
        await audio.play();
      }
    } catch (e) {
      setError(`Erro ao reproduzir: ${e.message}`);
    }
  };

  useEffect(() => {
    if (!pendingPlayRef.current || !shouldLoad || !finalSrc || loading) return;
    const audio = audioRef.current;
    if (!audio) return;
    pendingPlayRef.current = false;
    (async () => {
      try {
        await syncDuration();
        await audio.play();
      } catch (e) {
        setError(`Erro ao reproduzir: ${e.message}`);
      }
    })();
  }, [shouldLoad, finalSrc, loading, syncDuration]);

  const toggleMute = () => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.muted = !audio.muted;
    setMuted(audio.muted);
  };

  const handleProgressBarClick = (e) => {
    const audio = audioRef.current;
    if (!audio || !isValidDuration(duration)) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const percent = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    const seekTime = percent * duration;
    audio.currentTime = seekTime;
    setProgress(seekTime);
  };

  const toggleSpeed = () => {
    const newSpeed = speed === 1 ? 1.5 : speed === 1.5 ? 2 : 1;
    setSpeed(newSpeed);
    if (audioRef.current) audioRef.current.playbackRate = newSpeed;
  };

  const formatTime = (time) => {
    if (!isValidDuration(time) && time !== 0) return '--:--';
    const min = Math.floor(time / 60);
    const sec = Math.floor(time % 60);
    return `${min.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`;
  };

  const progressPercent = isValidDuration(duration)
    ? Math.min(100, Math.max(0, (progress / duration) * 100))
    : 0;

  const displayDuration = isValidDuration(duration) ? duration : progress;

  return (
    <div
      ref={containerRef}
      className={`flex flex-col gap-1 rounded-lg px-2 py-1 ${isCustomer ? 'bg-[#23272f]' : 'bg-[#009ca6]'} shadow`}
    >
      {error && (
        <div className="text-red-300 text-xs mb-1">
          {error}
          <button
            type="button"
            onClick={() => {
              setError(null);
              setShouldLoad(true);
              setLoading(true);
              audioRef.current?.load();
              syncDuration();
            }}
            className="ml-2 text-blue-300 underline hover:text-blue-200"
          >
            Tentar novamente
          </button>
        </div>
      )}
      {loading && shouldLoad && !error && (
        <div className="text-blue-300 text-xs mb-1">Carregando áudio...</div>
      )}
      <div className="flex items-center gap-2">
        <button type="button" onClick={togglePlay} className="p-1 text-white" disabled={loading && shouldLoad && !isLoaded}>
          {playing ? <Pause size={20} /> : <Play size={20} />}
        </button>
        <span className="text-xs text-white min-w-[72px] tabular-nums">
          {formatTime(progress)} / {formatTime(displayDuration)}
        </span>
        <button type="button" onClick={toggleSpeed} className="p-1 text-white flex items-center">
          <FastForward size={18} />
          <span className="ml-1 text-xs">{speed}x</span>
        </button>
        <a href={src || finalSrc || '#'} download target="_blank" rel="noopener noreferrer" className="p-1 text-white">
          <Download size={18} />
        </a>
        <button type="button" onClick={toggleMute} className="p-1 text-white">
          <Volume2 size={18} />
        </button>
      </div>
      <div
        className="w-full h-2 bg-white/25 rounded cursor-pointer overflow-hidden"
        onClick={handleProgressBarClick}
        role="slider"
        aria-valuemin={0}
        aria-valuemax={duration || 0}
        aria-valuenow={progress}
      >
        <div
          className="h-2 bg-white/90 rounded transition-[width] duration-75 ease-linear"
          style={{ width: `${progressPercent}%` }}
        />
      </div>
      <audio
        key={finalSrc || 'empty'}
        ref={audioRef}
        src={finalSrc || undefined}
        preload="none"
        onPlay={() => {
          setPlaying(true);
          setError(null);
        }}
        onPause={() => setPlaying(false)}
        onEnded={() => {
          setPlaying(false);
          setProgress(0);
        }}
        onError={() => {
          if (!shouldLoad || !finalSrc) return;
          const mediaError = audioRef.current?.error;
          let errorMessage = 'Erro ao carregar áudio';
          if (mediaError?.code === 2) errorMessage = 'Erro de rede';
          else if (mediaError?.code === 3) errorMessage = 'Erro de decodificação';
          else if (mediaError?.code === 4) errorMessage = 'Formato não suportado';
          setError(errorMessage);
          setLoading(false);
          setIsLoaded(false);
        }}
        {...(needsCrossOrigin ? { crossOrigin: 'anonymous' } : {})}
        style={{ display: 'none' }}
      />
    </div>
  );
}
