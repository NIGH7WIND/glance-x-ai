import queue
import threading
import re
import random
import sounddevice as sd
from pocket_tts import TTSModel, export_model_state
import os


class SpeechManager:
    """
    Pipeline: text_buffer -> gen_queue -> [gen_worker] -> audio_queue -> [play_worker]

    process_text_chunk() only does string splitting and queue.put() — never blocks.
    All model inference happens on gen_worker, off the caller's thread.
    """

    # Cap how many sentences can be queued ahead of playback (bounded lookahead).
    MAX_LOOKAHEAD = 2
    # Fallback cut for a sentence that's gone unusually long with no punctuation yet,
    # so we don't sit on silence waiting for a period that may never come soon.
    LONG_SENTENCE_WORD_LIMIT = 40
    # Short filler lines played instantly on turn start to mask generation latency.
    FILLER_PHRASES = [
    "Okay, let's see,",
    "Alright,",
    "So, let's see,",
    "Sure, one moment,",
    "Let's take a look,",
    "Okay, here goes,",
    ]

    def __init__(self, voice_name="alba"):
        self.voice_name = voice_name
        self.text_buffer = ""
        self.is_running = True
        self._filler_played = False

        # Two independent queues so generation and playback pipeline concurrently.
        self.gen_queue = queue.Queue()
        self.audio_queue = queue.Queue(maxsize=self.MAX_LOOKAHEAD)

        # Monotonically increasing "epoch" — bumped on stop()/interrupt so stale
        # in-flight generations/playback don't leak past a cancel.
        self._epoch = 0
        self._epoch_lock = threading.Lock()

        print("Loading Pocket-TTS model...")
        self.tts_model = TTSModel.load_model()

        state_file = f"{self.voice_name}_voice.safetensors"
        if os.path.exists(state_file):
            self.voice_state = self.tts_model.get_state_for_audio_prompt(state_file)
        else:
            self.voice_state = self.tts_model.get_state_for_audio_prompt(self.voice_name)
            export_model_state(self.voice_state, state_file)

        self._filler_audio = [
            self.tts_model.generate_audio(self.voice_state, phrase).numpy()
            for phrase in self.FILLER_PHRASES
        ]

        self.gen_thread = threading.Thread(target=self._gen_worker, daemon=True)
        self.gen_thread.start()

        self.playback_thread = threading.Thread(target=self._play_worker, daemon=True)
        self.playback_thread.start()

    # ---- called from the caller's thread (e.g. Qt/asyncio event loop) ----

    def process_text_chunk(self, chunk: str):
        """Accumulate streaming tokens; enqueue complete sentences for generation.
        Non-blocking: only string ops + Queue.put (unbounded gen_queue)."""
        self.text_buffer += chunk

        if not self._filler_played:
            self._play_filler()
            self._filler_played = True

        sentences = re.split(r'(?<=[.!?\n,])\s+', self.text_buffer)
        if len(sentences) > 1:
            for sentence in sentences[:-1]:
                clean = sentence.strip()
                if clean:
                    self._enqueue_for_generation(clean)
            self.text_buffer = sentences[-1]

        self._maybe_cut_long_sentence()

    def _play_filler(self):
        """Queue a pre-rendered filler line straight to playback (no gen-thread
        round trip) to mask generation latency while the real audio is produced."""
        with self._epoch_lock:
            epoch = self._epoch
        audio_data = random.choice(self._filler_audio)
        try:
            self.audio_queue.put_nowait((epoch, audio_data))
        except queue.Full:
            pass  # queue should be empty at turn start; skip filler rather than block

    def _maybe_cut_long_sentence(self):
        """If the pending sentence has run past LONG_SENTENCE_WORD_LIMIT with no
        terminal punctuation yet, cut it off (preferring a nearby comma) rather
        than risk a long silent wait for a period that may not come soon."""
        words = self.text_buffer.split()
        if len(words) < self.LONG_SENTENCE_WORD_LIMIT:
            return
        head = " ".join(words[: self.LONG_SENTENCE_WORD_LIMIT])
        comma_idx = self.text_buffer.find(",")
        if 0 < comma_idx <= len(head) + 20:
            head = self.text_buffer[: comma_idx + 1]
        clean = head.strip()
        if clean:
            self._enqueue_for_generation(clean)
            self.text_buffer = self.text_buffer[len(head):].lstrip()

    def finalize(self):
        """Flush any remaining buffered text at end of stream."""
        clean = self.text_buffer.strip()
        if clean:
            self._enqueue_for_generation(clean)
        self.text_buffer = ""
        self._filler_played = False

    def _enqueue_for_generation(self, text: str):
        with self._epoch_lock:
            epoch = self._epoch
        self.gen_queue.put((epoch, text))

    # ---- generation worker (off event-loop thread) ----

    def _gen_worker(self):
        while self.is_running:
            item = self.gen_queue.get()
            if item is None:
                break
            epoch, text = item

            with self._epoch_lock:
                current_epoch = self._epoch
            if epoch != current_epoch:
                continue  # stale text from before a stop()/interrupt — drop it

            try:
                audio_tensor = self.tts_model.generate_audio(self.voice_state, text)
                audio_data = audio_tensor.numpy()
            except Exception as e:
                print(f"TTS generation error: {e}")
                continue

            with self._epoch_lock:
                current_epoch = self._epoch
            if epoch != current_epoch:
                continue  # cancelled while generating — discard result

            # Blocks here if audio_queue is full (bounded lookahead) — this is
            # fine, it's the gen thread, not the caller/event-loop thread.
            while self.is_running:
                try:
                    self.audio_queue.put((epoch, audio_data), timeout=0.2)
                    break
                except queue.Full:
                    continue

    # ---- playback worker ----

    def _play_worker(self):
        while self.is_running:
            try:
                item = self.audio_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if item is None:
                break
            epoch, audio_data = item

            with self._epoch_lock:
                current_epoch = self._epoch
            if epoch != current_epoch:
                continue  # stale audio from a cancelled turn — skip playing it

            sd.play(audio_data, samplerate=self.tts_model.sample_rate)
            sd.wait()

    # ---- control ----

    def stop(self):
        """Interrupt current speech: stop playback immediately and drop
        everything queued/in-flight from before this point."""
        with self._epoch_lock:
            self._epoch += 1  # invalidates all in-flight/queued items

        sd.stop()

        for q in (self.gen_queue, self.audio_queue):
            with q.mutex:
                q.queue.clear()

        self.text_buffer = ""
        self._filler_played = False

    def shutdown(self):
        """Fully stop worker threads (call on app exit)."""
        self.is_running = False
        self.stop()
        self.gen_queue.put(None)
        try:
            self.audio_queue.put_nowait(None)
        except queue.Full:
            with self.audio_queue.mutex:
                self.audio_queue.queue.clear()
            self.audio_queue.put_nowait(None)