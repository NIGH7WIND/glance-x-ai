import queue
import threading
import re
import sounddevice as sd
from pocket_tts import TTSModel, export_model_state
import os

class SpeechManager:
    def __init__(self, voice_name="alba"):
        self.voice_name = voice_name
        self.audio_queue = queue.Queue()
        self.text_buffer = ""
        self.is_running = True
        
        # Load model
        print("Loading Pocket-TTS model...")
        self.tts_model = TTSModel.load_model()
        
        # Pre-cache voice state for low latency
        state_file = f"{self.voice_name}_voice.safetensors"
        if os.path.exists(state_file):
            self.voice_state = self.tts_model.get_state_for_audio_prompt(state_file)
        else:
            self.voice_state = self.tts_model.get_state_for_audio_prompt(self.voice_name)
            export_model_state(self.voice_state, state_file)

        # Worker thread for playing audio back sequentially
        self.playback_thread = threading.Thread(target=self._play_worker, daemon=True)
        self.playback_thread.start()

    def process_text_chunk(self, chunk: str):
        """Accumulates streaming tokens from LLM and queues full sentences for TTS."""
        self.text_buffer += chunk
        
        # Match sentences ending with punctuation or double linebreaks
        sentences = re.split(r'(?<=[.!?\n])\s+', self.text_buffer)
        
        # Process complete sentences, keep incomplete tail in buffer
        if len(sentences) > 1:
            for sentence in sentences[:-1]:
                clean_sentence = sentence.strip()
                if clean_sentence:
                    self._generate_and_queue(clean_sentence)
            self.text_buffer = sentences[-1]

    def finalize(self):
        """Flushes remaining text when LLM finishes streaming."""
        clean_sentence = self.text_buffer.strip()
        if clean_sentence:
            self._generate_and_queue(clean_sentence)
        self.text_buffer = ""

    def _generate_and_queue(self, text: str):
        """Generates PCM audio tensor and puts it into playback queue."""
        try:
            audio_tensor = self.tts_model.generate_audio(self.voice_state, text)
            # Convert PyTorch tensor to numpy array for sounddevice
            audio_data = audio_tensor.numpy()
            self.audio_queue.put(audio_data)
        except Exception as e:
            print(f"TTS Error: {e}")

    def _play_worker(self):
        """Worker loop reading numpy audio arrays and streaming to speakers."""
        while self.is_running:
            audio_data = self.audio_queue.get()
            if audio_data is None:
                break
            
            # Play audio blockingly on worker thread
            sd.play(audio_data, samplerate=self.tts_model.sample_rate)
            sd.wait()
            self.audio_queue.task_done()

    def stop(self):
        """Interrupt current speech generation and clear playback queue."""
        with self.audio_queue.mutex:
            self.audio_queue.queue.clear()
        sd.stop()