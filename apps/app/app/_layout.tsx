import { Stack } from 'expo-router';
import { SocketProvider } from '@/components/SocketContext';

export default function RootLayout() {
  return (
    <SocketProvider url="ws://your-server-url">
      <Stack />
    </SocketProvider>
  );
}