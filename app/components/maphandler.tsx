'use client';
import dynamic from 'next/dynamic';

const MapContainer = dynamic(
  () => import('react-leaflet').then((mod) => mod.MapContainer),
  { ssr: false }
);
const TileLayer = dynamic(
  () => import('react-leaflet').then((mod) => mod.TileLayer),
  { ssr: false }
);
const Marker = dynamic(
  () => import('react-leaflet').then((mod) => mod.Marker),
  { ssr: false }
);

import 'leaflet/dist/leaflet.css';
import L from 'leaflet';

// Fix default marker icon broken in Next.js
const icon = L.icon({
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
});

const locations = [
  { id: 1, lat: 41.8832, lng: -87.6324, label: 'Chicago' },
];



export default function Map({ onMarkerClick }: { onMarkerClick: (loc: any) => void }) {
  return (
    <MapContainer
      center={[41.8832, -87.6324] as [number, number]}
      zoom={15}
      style={{ height: '35rem', width: '100%' }}
    >
      <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      {locations.map((loc) => (
        <Marker key={loc.id} position={[loc.lat, loc.lng] as [number, number]} icon={icon} 
            eventHandlers={{
            click: () => onMarkerClick(loc),
        }} />
      ))}
    </MapContainer>
  );
}