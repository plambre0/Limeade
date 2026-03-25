import { useState } from 'react';
import MapHandler from './components/MapHandler';
import Sidebar from './components/Sidebar';
import Coordbar from './components/Coordbar';

export default function Home() {
  const [selected, setSelected] = useState<{ lat: number; lng: number; label: string } | null>(null);

  return (
    <main className="mx-auto w-full max-w-6xl px-8 py-8">
      <div className="flex flex-row gap-8 w-full">
        <div className="flex-[2]">
          <MapHandler onMarkerClick={setSelected} />
        </div>
        <div className="flex-[1] flex flex-col gap-4">
          <Sidebar />
          <Coordbar selected={selected} />
        </div>
      </div>
    </main>
  );
}
