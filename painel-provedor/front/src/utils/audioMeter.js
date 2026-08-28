/**
 * Mede o nível (volume) de um MediaStream de áudio em tempo real via Web Audio API.
 * Usado para dar feedback visual (ex.: pulso no card de ligação) quando há som chegando.
 *
 * @param {MediaStream} stream
 * @param {(db: number) => void} onDb - chamado a cada frame com o nível em dB, entre -60 (silêncio) e 0 (pico).
 * @returns {() => void} função para parar a medição e liberar recursos.
 */
export function attachMeter(stream, onDb) {
  if (!stream || typeof stream.getAudioTracks !== 'function' || stream.getAudioTracks().length === 0) {
    return () => {};
  }
  let ctx;
  try {
    ctx = new (window.AudioContext || window.webkitAudioContext)();
  } catch {
    // navegador sem suporte a Web Audio API: segue sem medidor
    return () => {};
  }

  let src;
  let analyser;
  try {
    src = ctx.createMediaStreamSource(stream);
    analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    src.connect(analyser);
  } catch {
    try {
      ctx.close();
    } catch {
      // contexto já pode estar fechado
    }
    return () => {};
  }

  const data = new Float32Array(analyser.fftSize);
  let stopped = false;
  let frame = null;

  const tick = () => {
    if (stopped) return;
    analyser.getFloatTimeDomainData(data);
    let sum = 0;
    for (let i = 0; i < data.length; i += 1) sum += data[i] * data[i];
    const rms = Math.sqrt(sum / data.length);
    const db = rms > 0 ? Math.max(-60, Math.min(0, 20 * Math.log10(rms))) : -60;
    onDb(db);
    frame = requestAnimationFrame(tick);
  };
  frame = requestAnimationFrame(tick);

  return () => {
    stopped = true;
    if (frame) cancelAnimationFrame(frame);
    try {
      src.disconnect();
      analyser.disconnect();
      ctx.close();
    } catch {
      // recursos já podem ter sido liberados
    }
  };
}

/** Converte dB (-60..0) em um nível 0..1 já com curva suave, focado em fala. */
export function dbToLevel(db, { floor = -55, ceil = -12, curve = 1.6 } = {}) {
  const norm = Math.max(0, Math.min(1, (db - floor) / (ceil - floor)));
  return Math.pow(norm, curve);
}
