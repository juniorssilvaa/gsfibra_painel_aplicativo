import { ExternalLink } from 'lucide-react';
import { useMemo } from 'react';
import mapsPin from '../assets/maps-pin.png';

/**
 * Extrai coordenadas de uma mensagem (attrs ou texto legado da IA).
 */
export function getMessageLocation(msg) {
  if (!msg) return null;
  const attrs = msg.additional_attributes || {};
  let lat = attrs.latitude ?? attrs.lat;
  let lng = attrs.longitude ?? attrs.lng ?? attrs.lon;

  if (lat == null || lng == null) {
    const content = String(msg.content || '');
    const latM = content.match(/latitude\s*=\s*(-?\d+(?:[.,]\d+)?)/i);
    const lngM = content.match(/longitude\s*=\s*(-?\d+(?:[.,]\d+)?)/i);
    if (latM && lngM) {
      lat = latM[1].replace(',', '.');
      lng = lngM[1].replace(',', '.');
    }
  }

  if (lat == null || lng == null) return null;

  const latN = Number(lat);
  const lngN = Number(lng);
  if (!Number.isFinite(latN) || !Number.isFinite(lngN)) return null;

  return {
    lat: latN,
    lng: lngN,
    name: (attrs.location_name || attrs.name || '').trim() || null,
    address: (attrs.location_address || attrs.address || '').trim() || null,
  };
}

function latLngToWorldPixels(lat, lng, zoom) {
  const n = 2 ** zoom;
  const tileSize = 256;
  const x = ((lng + 180) / 360) * n * tileSize;
  const sinLat = Math.sin((lat * Math.PI) / 180);
  const y =
    (0.5 - Math.log((1 + sinLat) / (1 - sinLat)) / (4 * Math.PI)) * n * tileSize;
  return { x, y, n, tileSize };
}

/**
 * Preview de mapa com ruas (tiles escuros estilo WhatsApp), sem API key.
 */
function DarkStreetMapPreview({ lat, lng, width = 280, height = 150, zoom = 16 }) {
  const tiles = useMemo(() => {
    const { x: worldX, y: worldY, n, tileSize } = latLngToWorldPixels(lat, lng, zoom);
    const left = worldX - width / 2;
    const top = worldY - height / 2;
    const startX = Math.floor(left / tileSize);
    const startY = Math.floor(top / tileSize);
    const endX = Math.floor((left + width) / tileSize);
    const endY = Math.floor((top + height) / tileSize);

    const list = [];
    for (let ty = startY; ty <= endY; ty++) {
      if (ty < 0 || ty >= n) continue;
      for (let tx = startX; tx <= endX; tx++) {
        const wrappedX = ((tx % n) + n) % n;
        list.push({
          key: `${zoom}-${wrappedX}-${ty}`,
          url: `https://basemaps.cartocdn.com/dark_all/${zoom}/${wrappedX}/${ty}.png`,
          left: tx * tileSize - left,
          top: ty * tileSize - top,
          size: tileSize,
        });
      }
    }
    return list;
  }, [lat, lng, width, height, zoom]);

  return (
    <div
      className="relative overflow-hidden bg-zinc-900"
      style={{ width, height }}
    >
      {tiles.map((t) => (
        <img
          key={t.key}
          src={t.url}
          alt=""
          draggable={false}
          className="absolute max-w-none select-none pointer-events-none"
          style={{
            left: t.left,
            top: t.top,
            width: t.size,
            height: t.size,
          }}
        />
      ))}
      {/* Ícone de mapa (Icons8 fluency) no centro do ponto */}
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center z-[1]">
        <img
          src={mapsPin}
          alt=""
          draggable={false}
          className="w-11 h-11 drop-shadow-[0_2px_6px_rgba(0,0,0,0.75)] -translate-y-[14px] select-none"
        />
      </div>
    </div>
  );
}

/**
 * Card estilo WhatsApp para mensagem de localização.
 */
export default function LocationMessageCard({ lat, lng, name, address, isCustomer = false }) {
  const mapsUrl = `https://www.google.com/maps?q=${lat},${lng}`;
  const label = name || address || 'Localização';
  const subtitle = name && address ? address : `${lat.toFixed(5)}, ${lng.toFixed(5)}`;

  return (
    <a
      href={mapsUrl}
      target="_blank"
      rel="noopener noreferrer"
      className="block w-[260px] sm:w-[280px] overflow-hidden rounded-xl no-underline group shadow-md"
      title="Abrir no Google Maps"
    >
      <DarkStreetMapPreview lat={lat} lng={lng} width={280} height={150} zoom={16} />
      <div
        className={`px-3 py-2.5 flex items-start gap-2 ${
          isCustomer ? 'bg-[#3d4a5c] text-white' : 'bg-[#1e88e5] text-white'
        }`}
      >
        <img src={mapsPin} alt="" className="h-5 w-5 mt-0.5 shrink-0 object-contain" />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold truncate leading-tight">{label}</div>
          <div className="text-[11px] opacity-80 truncate mt-0.5">{subtitle}</div>
        </div>
        <ExternalLink className="h-3.5 w-3.5 mt-0.5 shrink-0 opacity-70 group-hover:opacity-100" />
      </div>
    </a>
  );
}
