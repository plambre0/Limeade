import Alert from '@/components/Alert-sound';
import CameraPage from '@/components/camera-request';
import { View } from 'react-native';

export default function HomeScreen() {
  return(
        <View>
          <CameraPage />
          <Alert />
        </View>
        );
}
