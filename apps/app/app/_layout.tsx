import { Stack } from 'expo-router';
import { SocketProvider } from '@/components/SocketContext';
import { WS_URL } from '@/constants/api';

export default function RootLayout() {
  return (
    <SocketProvider url={WS_URL}>
      <Stack />
    </SocketProvider>
  );
}