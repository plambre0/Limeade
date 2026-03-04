import { useQuery } from '@tanstack/react-query';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { CircleMarker, MapContainer, Popup, TileLayer } from 'react-leaflet';

const API = 'http://localhost:8000';

interface Hazard {
  id: number;
  latitude: number;
  longitude: number;
  hazard_type: string;
  severity: number;
  description: string | null;
  created_at: string;
}

const severityColors: Record<number, string> = {
  1: '#00DD00',
  2: '#AAFF00',
  3: '#FFD600',
  4: '#FF6600',
  5: '#FF1744',
};

export default function MapHandler({ onMarkerClick }: { onMarkerClick: (loc: any) => void }) {
  const { data: hazards = [] } = useQuery<Hazard[]>({
    queryKey: ['hazards-map'],
    queryFn: () =>
      fetch(`${API}/hazards?lat=41.88&lng=-87.63&radius_km=100`).then((r) => r.json()),
    refetchInterval: 5000,
  });

  return (
    <MapContainer
      center={[41.8832, -87.6324]}
      zoom={15}
      style={{ height: '35rem', width: '100%', borderRadius: '10px', border: '1px solid #333' }}
    >
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        attribution='&copy; <a href="https://carto.com/">CARTO</a>'
      />
      {hazards.map((h) => (
        <CircleMarker
          key={h.id}
          center={[h.latitude, h.longitude]}
          radius={6 + h.severity * 2}
          pathOptions={{
            color: severityColors[h.severity] ?? '#ff9800',
            fillColor: severityColors[h.severity] ?? '#ff9800',
            fillOpacity: 0.7,
          }}
          eventHandlers={{
            click: () =>
              onMarkerClick({
                lat: h.latitude,
                lng: h.longitude,
                label: h.hazard_type,
              }),
          }}
        >
          <Popup>
            <strong style={{ textTransform: 'capitalize' }}>
              {h.hazard_type.replace('_', ' ')}
            </strong>
            <br />
            Severity: {h.severity}/5
            {h.description && (
              <>
                <br />
                {h.description}
              </>
            )}
            <br />
            <small>{new Date(h.created_at).toLocaleString()}</small>
          </Popup>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}
