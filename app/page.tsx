'use client';

import Map from "./components/maphandler"
import Card from "./components/sidebar"
import Coords from "./components/coordbar"
import {useState} from 'react'

export default function Home() {
  const [selected, setSelected] = useState<{ lat: number; lng: number; label: string } | null>(null);

    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-50 font-sans">
        <main className="flex min-h-screen w-full max-w-6xl flex-col items-center justify-between py-16 px-8 sm:items-start">
          <div className="flex flex-row gap-8 w-full">
            <div className="flex-[2]"><Map onMarkerClick={setSelected}/></div>
            <div className="flex-[1] flex flex-col gap-4">
                <Card />
                <Coords selected={selected}/> 
              </div>
          </div>
        </main>
      </div>
    );
}
