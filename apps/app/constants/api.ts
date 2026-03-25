import Constants from 'expo-constants';

const devHost = Constants.expoConfig?.hostUri?.split(':')[0] ?? 'localhost';
const API_PORT = 8000;

export const API_BASE_URL = __DEV__ ? `http://${devHost}:${API_PORT}` : 'https://api.example.com';

export const WS_URL = __DEV__ ? `ws://${devHost}:${API_PORT}/ws` : 'wss://api.example.com/ws';
