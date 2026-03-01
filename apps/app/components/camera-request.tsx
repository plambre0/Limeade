import { CameraView, CameraType, useCameraPermissions } from 'expo-camera';
import { useState, useRef, useEffect } from 'react';
import { Button, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useSocket } from './SocketContext';
import * as FileSystem from 'expo-file-system';

const CHUNK_DURATION_MS = 1000; // 1 second chunks

export default function CameraPage() {
  const cameraRef = useRef<CameraView | null>(null);
  const [facing, setFacing] = useState<CameraType>('back');
  const [permission, requestPermission] = useCameraPermissions();
  const { isConnected, send } = useSocket();
  const streamingRef = useRef(false);

  useEffect(() => {
    return () => { streamingRef.current = false; };
  }, []);

  async function startStream() {
    if (streamingRef.current || !cameraRef.current) return;
    streamingRef.current = true;

    while (streamingRef.current && isConnected) {
      try {
        const recording = cameraRef.current.recordAsync({
          maxDuration: CHUNK_DURATION_MS / 1000,
        });

        // wait for the chunk to finish
        const result = await recording;

        if (result?.uri && streamingRef.current) {
          const base64 = await FileSystem.readAsStringAsync(result.uri, {
            encoding: 'base64',
          });
          send(base64);
          // clean up chunk
          await FileSystem.deleteAsync(result.uri, { idempotent: true });
        }
      } catch (e) {
        console.warn('Stream chunk error:', e);
        break;
      }
    }
  }

  function stopStream() {
    streamingRef.current = false;
    cameraRef.current?.stopRecording();
  }

  if (!permission) return <View />;
  if (!permission.granted) {
    return (
      <View style={styles.container}>
        <Text style={styles.message}>We need your permission to show the camera</Text>
        <Button onPress={requestPermission} title="grant permission" />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <CameraView
        ref={cameraRef}
        style={styles.camera}
        facing={facing}
        mode="video"
        onCameraReady={startStream}
      />
      <View style={styles.buttonContainer}>
        <TouchableOpacity style={styles.button} onPress={() => setFacing(f => f === 'back' ? 'front' : 'back')}>
          <Text style={styles.text}>Flip</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.button} onPress={stopStream}>
          <Text style={styles.text}>Stop</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center' },
  message: { textAlign: 'center', paddingBottom: 10 },
  camera: { flex: 1 },
  buttonContainer: {
    position: 'absolute',
    bottom: 64,
    flexDirection: 'row',
    width: '100%',
    paddingHorizontal: 64,
  },
  button: { flex: 1, alignItems: 'center' },
  text: { fontSize: 24, fontWeight: 'bold', color: 'white' },
});