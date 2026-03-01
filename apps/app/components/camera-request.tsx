import { CameraView, useCameraPermissions } from 'expo-camera';
import { useEffect, useRef, useState } from 'react';
import { Button, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useSocket } from './SocketContext';

export default function CameraPage() {
  const cameraRef = useRef<CameraView | null>(null);
  const [permission, requestPermission] = useCameraPermissions();
  const { send } = useSocket();
  const streamingRef = useRef(false);
  const [isStreaming, setIsStreaming] = useState(false);

  useEffect(() => {
    return () => { streamingRef.current = false; };
  }, []);

  async function startStream() {
    if (streamingRef.current || !cameraRef.current) return;
    streamingRef.current = true;
    setIsStreaming(true);

    while (streamingRef.current) {
      try {
        const photo = await cameraRef.current?.takePictureAsync({
          base64: true,
          quality: 0.3,
          skipProcessing: true,
          imageType: 'jpg',
          shutterSound: false,
        });
        if (photo?.base64 && streamingRef.current) {
          send(JSON.stringify({
            image: photo.base64,
            latitude: 0,
            longitude: 0,
          }));
        }
      } catch (e) {
        console.warn('Capture error:', e);
      }
    }
  }

  function stopStream() {
    streamingRef.current = false;
    setIsStreaming(false);
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
        facing="back"
        animateShutter={false}
      />
      <View style={styles.buttonContainer}>
        <TouchableOpacity style={styles.button} onPress={isStreaming ? stopStream : startStream}>
          <Text style={styles.text}>{isStreaming ? 'Stop' : 'Start'}</Text>
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
    justifyContent: 'center',
  },
  button: { paddingHorizontal: 32, paddingVertical: 16 },
  text: { fontSize: 24, fontWeight: 'bold', color: 'white' },
});
