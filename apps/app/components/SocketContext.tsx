import { createContext, useContext, useEffect, useRef, useState, useCallback, type ReactNode } from 'react';
import { AppState } from 'react-native';

type SocketContextValue = {
  isConnected: boolean;
  send: (data: string) => void;
  sendAndWait: (data: string) => Promise<string>;
  lastMessage: string | null;
};

const SocketContext = createContext<SocketContextValue>({
  isConnected: false,
  send: () => {},
  sendAndWait: () => Promise.resolve(''),
  lastMessage: null,
});

export function useSocket() {
  return useContext(SocketContext);
}

export function SocketProvider({ url, children }: { url: string; children: ReactNode }) {
  const wsRef = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<string | null>(null);

  const pendingResolve = useRef<((data: string) => void) | null>(null);

  const connect = useCallback(() => {
    wsRef.current?.close();
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setIsConnected(true);
    ws.onclose = () => setIsConnected(false);
    ws.onerror = () => setIsConnected(false);
    ws.onmessage = (e) => {
      setLastMessage(e.data);
      if (pendingResolve.current) {
        pendingResolve.current(e.data);
        pendingResolve.current = null;
      }
    };
  }, [url]);

  useEffect(() => {
    connect();

    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active') {
        if (wsRef.current?.readyState !== WebSocket.OPEN) {
          connect();
        }
      }
    });

    return () => {
      sub.remove();
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect]);

  function send(data: string) {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(data);
    }
  }

  function sendAndWait(data: string): Promise<string> {
    return new Promise((resolve) => {
      pendingResolve.current = resolve;
      send(data);
    });
  }

  return (
    <SocketContext.Provider value={{ isConnected, send, sendAndWait, lastMessage }}>
      {children}
    </SocketContext.Provider>
  );
}
