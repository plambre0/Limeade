import * as Haptics from 'expo-haptics';
import { setAudioModeAsync, useAudioPlayer } from 'expo-audio';
import { useEffect } from 'react';
import { View, Button } from 'react-native';


export default function Alert() {
    
  const audioSource = require("./audio/videoplayback.mp3");
  const player = useAudioPlayer(audioSource);


  const handlePlay = () => {
    // Start playback - this will continue in the background
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);

    player.play();
  };

  const handleStop = () => {
    player.pause();

  };

  return (
    <View>
      <Button title="Play" onPress={handlePlay} />
      <Button title="Stop" onPress={handleStop} />
    </View>
  );

}

