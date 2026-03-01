import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';

type SocketContextValue = {
  isConnected: boolean;
  send: (data: string) => void;
  lastMessage: string | null;
};

const SocketContext = createContext<SocketContextValue>({
  isConnected: false,
  send: () => {},
  lastMessage: null,
});

export function useSocket() {
  return useContext(SocketContext);
}

export function SocketProvider({ url, children }: { url: string; children: ReactNode }) {
  const wsRef = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<string | null>(null);

  useEffect(() => {
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setIsConnected(true);
    ws.onclose = () => setIsConnected(false);
    ws.onerror = () => setIsConnected(false);
    ws.onmessage = (e) => setLastMessage(e.data);

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [url]);

  function send(data: string) {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(data);
    }
  }

  return (
    <SocketContext.Provider value={{ isConnected, send, lastMessage }}>
      {children}
    </SocketContext.Provider>
  );
}
