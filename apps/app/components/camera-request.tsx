import { CameraView, useCameraPermissions } from 'expo-camera';
import * as Haptics from 'expo-haptics';
import * as Location from 'expo-location';
import * as Speech from 'expo-speech';
import { useEffect, useRef, useState } from 'react';
import { Button, StyleSheet, Text, TouchableOpacity, Vibration, View } from 'react-native';
import { useSocket } from './SocketContext';

function getAlert(detections: any[]): string | null {
  const hasHazard = detections.some((d: any) => d.category === 'hazard');
  const hasPedestrian = detections.some((d: any) => d.category === 'pedestrian');
  const hasVehicle = detections.some((d: any) => d.category === 'vehicle');
  if (hasHazard) return "Pothole ahead";
  if (hasVehicle) return "Vehicle nearby";
  if (hasPedestrian) return "Pedestrian ahead";
  return null;
}

export default function CameraPage() {
  const cameraRef = useRef<CameraView | null>(null);
  const [permission, requestPermission] = useCameraPermissions();
  const { sendAndWait, lastMessage } = useSocket();
  const streamingRef = useRef(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const locationRef = useRef<{ latitude: number; longitude: number }>({ latitude: 0, longitude: 0 });
  const lastSpoke = useRef(0);

  // Haptic + voice feedback based on danger score
  useEffect(() => {
    if (!lastMessage) return;
    try {
      const msg = JSON.parse(lastMessage);

      if (msg.type === 'assessment') {
          const a = msg.assessment;
          if (!a || !a.is_real_threat) return;
          // Vibration intensity based on Claude's urgency (1-5)
          if (a.urgency >= 5) {
              Vibration.vibrate([0, 500, 200, 500, 200, 500]);
          } else if (a.urgency >= 4) {
              Vibration.vibrate([0, 500, 200, 500]);
          } else if (a.urgency >= 3) {
              Vibration.vibrate(400);
          } else {
              Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);
          }
          // Speak Claude's threat summary
          Speech.stop();
          Speech.speak(a.threat_summary, { rate: 1.1 });
      }else if (msg.type === 'detection'){
       const score = msg.danger_score ?? 0;
       if (score >= 0.8) {
           Vibration.vibrate([0, 500, 200, 500]);
       } else if (score >= 0.5) {
           Vibration.vibrate(400);
       } else if (score >= 0.3) {
           Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
       }
       if (score >= 0.3 && Date.now() - lastSpoke.current > 5000) {
           const quip = getAlert(msg.detections ?? []);
           if (quip) {
               lastSpoke.current = Date.now();
               Speech.speak(quip, { rate: 1.1 });
           }
       }
    }
    } catch (e) {
      console.error('Error processing message:', e);
    }
  }, [lastMessage]);

  useEffect(() => {
    (async () => {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status === 'granted') {
        await Location.watchPositionAsync(
          { accuracy: Location.Accuracy.High, distanceInterval: 1 },
          (loc) => {
            locationRef.current = {
              latitude: loc.coords.latitude,
              longitude: loc.coords.longitude,
            };
          },
        );
      }
    })();
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
          await sendAndWait(JSON.stringify({
            image: photo.base64,
            ...locationRef.current,
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
        pictureSize="640x480"
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
