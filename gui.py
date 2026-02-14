import difflib
import io
import json
import queue
import threading
import urllib.error
import urllib.parse
import urllib.request
import warnings
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox

import numpy as np
import soundcard as sc
import soundfile as sf


SAMPLE_RATE = 48000
BLOCKSIZE = 4096
STREAM_TARGET_SR = 16000


class ListenoogaApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("listenooga - Mic + Systemaudio Recorder")

        self.is_recording = False
        self.mic_buffer = []
        self.loop_buffer = []
        self.mic_stream = None
        self.loop_stream = None
        self._mic_devices = []
        self._speaker_devices = []
        self._stream_queue = None
        self._stream_thread = None
        self._stream_stop = None
        self._stream_buffer = None
        self._stream_window_frames = 0
        self._stream_overlap_frames = 0
        self._stream_hop_frames = 0
        self._stream_input_rate = SAMPLE_RATE
        self._stream_enabled = False
        self._stream_url = ""
        self._stream_language = ""
        self._stream_translate = False
        self._stream_source = "Mic"
        self._stream_window_sec = 5.0
        self._stream_overlap_sec = 1.0
        self._transcript_tokens = []
        self._last_window_tokens = []
        self._style = ttk.Style()
        try:
            self._style.theme_use("clam")
        except Exception:  # noqa: BLE001
            pass
        self._style.configure("Mic.Horizontal.TProgressbar", troughcolor="#e6e6e6", background="#2f7d32")
        self._style.configure("Sys.Horizontal.TProgressbar", troughcolor="#e6e6e6", background="#1565c0")

        self._build_ui()
        self._load_devices()

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=10)
        main.grid(row=0, column=0, sticky="nsew")

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # Device selection
        ttk.Label(main, text="Mikrofon-Device:").grid(row=0, column=0, sticky="w")
        self.mic_combo = ttk.Combobox(main, state="readonly", width=60)
        self.mic_combo.grid(row=0, column=1, sticky="ew", pady=2)

        ttk.Label(main, text="Ausgabe-Device (fur Loopback):").grid(row=1, column=0, sticky="w")
        self.out_combo = ttk.Combobox(main, state="readonly", width=60)
        self.out_combo.grid(row=1, column=1, sticky="ew", pady=2)

        ttk.Label(main, text="Loopback-Device (optional):").grid(row=2, column=0, sticky="w")
        self.loop_combo = ttk.Combobox(main, state="readonly", width=60)
        self.loop_combo.grid(row=2, column=1, sticky="ew", pady=2)

        ttk.Label(main, text="Dateiname:").grid(row=3, column=0, sticky="w")
        self.filename_var = tk.StringVar(value="recording")
        self.filename_entry = ttk.Entry(main, textvariable=self.filename_var, width=30)
        self.filename_entry.grid(row=3, column=1, sticky="w", pady=2)

        ttk.Label(main, text="Samplerate:").grid(row=4, column=0, sticky="w")
        self.samplerate_var = tk.IntVar(value=SAMPLE_RATE)
        self.samplerate_spin = ttk.Spinbox(
            main,
            values=(22050, 44100, 48000),
            textvariable=self.samplerate_var,
            width=10,
            state="readonly",
        )
        self.samplerate_spin.grid(row=4, column=1, sticky="w", pady=2)

        ttk.Label(main, text="Blocksize:").grid(row=5, column=0, sticky="w")
        self.blocksize_var = tk.IntVar(value=BLOCKSIZE)
        self.blocksize_spin = ttk.Spinbox(
            main,
            values=(512, 1024, 2048, 4096, 8192),
            textvariable=self.blocksize_var,
            width=10,
            state="readonly",
        )
        self.blocksize_spin.grid(row=5, column=1, sticky="w", pady=2)

        ttk.Label(main, text="Realtime-Transkription:").grid(row=6, column=0, sticky="w")
        self.stream_enabled_var = tk.BooleanVar(value=False)
        self.stream_enabled_check = ttk.Checkbutton(main, variable=self.stream_enabled_var, text="Aktiv")
        self.stream_enabled_check.grid(row=6, column=1, sticky="w", pady=2)

        ttk.Label(main, text="Whisper Server URL:").grid(row=7, column=0, sticky="w")
        self.stream_url_var = tk.StringVar(value="http://127.0.0.1:9080/inference")
        self.stream_url_entry = ttk.Entry(main, textvariable=self.stream_url_var, width=50)
        self.stream_url_entry.grid(row=7, column=1, sticky="w", pady=2)

        ttk.Label(main, text="Fenster (s):").grid(row=8, column=0, sticky="w")
        self.stream_window_sec_var = tk.DoubleVar(value=5.0)
        self.stream_window_spin = ttk.Spinbox(
            main,
            from_=4.0,
            to=6.0,
            increment=0.5,
            textvariable=self.stream_window_sec_var,
            width=10,
        )
        self.stream_window_spin.grid(row=8, column=1, sticky="w", pady=2)

        ttk.Label(main, text="Ueberlappung (s):").grid(row=9, column=0, sticky="w")
        self.stream_overlap_sec_var = tk.DoubleVar(value=1.0)
        self.stream_overlap_spin = ttk.Spinbox(
            main,
            from_=0.0,
            to=3.0,
            increment=0.5,
            textvariable=self.stream_overlap_sec_var,
            width=10,
        )
        self.stream_overlap_spin.grid(row=9, column=1, sticky="w", pady=2)

        ttk.Label(main, text="Quelle:").grid(row=10, column=0, sticky="w")
        self.stream_source_var = tk.StringVar(value="Mic")
        self.stream_source_combo = ttk.Combobox(
            main,
            state="readonly",
            values=("Mic", "Systemaudio", "Mix"),
            textvariable=self.stream_source_var,
            width=15,
        )
        self.stream_source_combo.grid(row=10, column=1, sticky="w", pady=2)

        ttk.Label(main, text="Sprache (optional):").grid(row=11, column=0, sticky="w")
        self.stream_lang_var = tk.StringVar(value="de")
        self.stream_lang_entry = ttk.Entry(main, textvariable=self.stream_lang_var, width=10)
        self.stream_lang_entry.grid(row=11, column=1, sticky="w", pady=2)

        ttk.Label(main, text="Ubersetzen (EN):").grid(row=12, column=0, sticky="w")
        self.stream_translate_var = tk.BooleanVar(value=False)
        self.stream_translate_check = ttk.Checkbutton(main, variable=self.stream_translate_var, text="Translate")
        self.stream_translate_check.grid(row=12, column=1, sticky="w", pady=2)

        ttk.Label(main, text="Mic-Gain (x):").grid(row=13, column=0, sticky="w")
        self.mic_gain_var = tk.DoubleVar(value=50.0)
        self.mic_gain_spin = ttk.Spinbox(
            main,
            from_=0.1,
            to=100.0,
            increment=5.0,
            textvariable=self.mic_gain_var,
            width=10,
        )
        self.mic_gain_spin.grid(row=13, column=1, sticky="w", pady=2)

        ttk.Label(main, text="Mic-Pegel:").grid(row=14, column=0, sticky="w")
        self.mic_level_var = tk.StringVar(value="--")
        self.mic_level_label = ttk.Label(main, textvariable=self.mic_level_var)
        self.mic_level_label.grid(row=14, column=1, sticky="w", pady=2)
        self.mic_level_bar = ttk.Progressbar(
            main,
            length=240,
            mode="determinate",
            maximum=100.0,
            style="Mic.Horizontal.TProgressbar",
        )
        self.mic_level_bar.grid(row=14, column=1, sticky="e", padx=5)

        ttk.Label(main, text="System-Pegel:").grid(row=15, column=0, sticky="w")
        self.loop_level_var = tk.StringVar(value="--")
        self.loop_level_label = ttk.Label(main, textvariable=self.loop_level_var)
        self.loop_level_label.grid(row=15, column=1, sticky="w", pady=2)
        self.loop_level_bar = ttk.Progressbar(
            main,
            length=240,
            mode="determinate",
            maximum=100.0,
            style="Sys.Horizontal.TProgressbar",
        )
        self.loop_level_bar.grid(row=15, column=1, sticky="e", padx=5)

        # Buttons
        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=16, column=0, columnspan=2, pady=10, sticky="ew")

        self.refresh_btn = ttk.Button(btn_frame, text="Devices neu laden", command=self._load_devices)
        self.refresh_btn.grid(row=0, column=0, padx=5)

        self.start_btn = ttk.Button(btn_frame, text="Aufnahme starten", command=self.start_recording)
        self.start_btn.grid(row=0, column=1, padx=5)

        self.stop_btn = ttk.Button(btn_frame, text="Stop", command=self.stop_recording, state="disabled")
        self.stop_btn.grid(row=0, column=2, padx=5)

        # Status
        self.status_var = tk.StringVar(value="Bereit.")
        self.status_label = ttk.Label(main, textvariable=self.status_var)
        self.status_label.grid(row=17, column=0, columnspan=2, sticky="w", pady=5)

        transcript_frame = ttk.Frame(main)
        transcript_frame.grid(row=18, column=0, columnspan=2, sticky="ew")
        ttk.Label(transcript_frame, text="Transkript:").grid(row=0, column=0, sticky="w")
        self.clear_transcript_btn = ttk.Button(
            transcript_frame,
            text="Transkript leeren",
            command=self._clear_transcript,
        )
        self.clear_transcript_btn.grid(row=0, column=1, sticky="e")
        transcript_frame.columnconfigure(0, weight=1)
        transcript_frame.columnconfigure(1, weight=0)

        self.transcript_box = tk.Text(main, height=8, wrap="word")
        self.transcript_box.grid(row=19, column=0, columnspan=2, sticky="nsew", pady=4)
        self.transcript_box.configure(state="disabled")

        main.columnconfigure(1, weight=1)
        main.rowconfigure(19, weight=1)

    def _load_devices(self) -> None:
        try:
            mics = sc.all_microphones(include_loopback=False)
            loop_mics = sc.all_microphones(include_loopback=True)
            speakers = sc.all_speakers()
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Fehler", f"Audio-Devices konnten nicht geladen werden:\n{e}")
            return

        self._mic_devices = list(mics)
        self._loop_devices = list(loop_mics)
        self._speaker_devices = list(speakers)

        mic_choices = [f"[{idx}] {dev.name}" for idx, dev in enumerate(self._mic_devices)]
        loop_choices = [f"[{idx}] {dev.name}" for idx, dev in enumerate(self._loop_devices)]
        out_choices = [f"[{idx}] {dev.name}" for idx, dev in enumerate(self._speaker_devices)]

        self.mic_combo["values"] = mic_choices
        self.loop_combo["values"] = loop_choices
        self.out_combo["values"] = out_choices

        if mic_choices and not self.mic_combo.get():
            self.mic_combo.current(0)
        if loop_choices and not self.loop_combo.get():
            for i, entry in enumerate(loop_choices):
                if "loopback" in entry.lower() or "loop-back" in entry.lower():
                    self.loop_combo.current(i)
                    break
        if out_choices and not self.out_combo.get():
            self.out_combo.current(0)

        self.status_var.set("Devices aktualisiert.")

    def _parse_device_index(self, entry: str) -> int:
        try:
            start = entry.find("[") + 1
            end = entry.find("]")
            return int(entry[start:end])
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"Konnte Device-Index nicht aus '{entry}' lesen") from e

    def start_recording(self) -> None:
        if self.is_recording:
            return

        if not self.mic_combo.get() or not self.out_combo.get():
            messagebox.showwarning("Hinweis", "Bitte Mikrofon- und Ausgabe-Device auswahlen.")
            return

        try:
            mic_idx = self._parse_device_index(self.mic_combo.get())
            out_idx = self._parse_device_index(self.out_combo.get())
        except ValueError as e:
            messagebox.showerror("Fehler", str(e))
            return

        self.is_recording = True
        self.mic_buffer.clear()
        self.loop_buffer.clear()

        self._stream_enabled = bool(self.stream_enabled_var.get())
        self._stream_url = (self.stream_url_var.get() or "").strip()
        self._stream_language = (self.stream_lang_var.get() or "").strip()
        self._stream_translate = bool(self.stream_translate_var.get())
        self._stream_source = (self.stream_source_var.get() or "Mic").strip()
        self._stream_window_sec = float(self.stream_window_sec_var.get() or 5.0)
        self._stream_overlap_sec = float(self.stream_overlap_sec_var.get() or 1.0)

        self.start_btn["state"] = "disabled"
        self.stop_btn["state"] = "normal"
        self.refresh_btn["state"] = "disabled"
        self.status_var.set("Aufnahme laeuft...")

        threading.Thread(
            target=self._record_worker,
            args=(mic_idx, out_idx),
            daemon=True,
        ).start()

    def stop_recording(self) -> None:
        if not self.is_recording:
            return
        self.is_recording = False
        self.status_var.set("Stop angefordert...")

    def _record_worker(self, mic_idx: int, out_idx: int) -> None:
        try:
            mic_dev = self._mic_devices[mic_idx]
            speaker_dev = self._speaker_devices[out_idx]
        except IndexError:
            self.root.after(
                0,
                lambda: messagebox.showerror("Fehler", "Ungultige Device-Auswahl."),
            )
            self.is_recording = False
            return

        loopback_mic = None
        if self.loop_combo.get():
            try:
                loop_idx = self._parse_device_index(self.loop_combo.get())
                loopback_mic = self._loop_devices[loop_idx]
            except Exception:  # noqa: BLE001
                loopback_mic = None
        if loopback_mic is None:
            loopback_mic = self._find_loopback_microphone(speaker_dev)
        if loopback_mic is None:
            self.root.after(
                0,
                lambda: messagebox.showerror(
                    "Fehler",
                    "Loopback konnte nicht erstellt werden. Bitte anderes Ausgabegerat wahlen.",
                ),
            )
            self.is_recording = False
            return

        samplerate = int(self.samplerate_var.get() or SAMPLE_RATE)
        blocksize = int(self.blocksize_var.get() or BLOCKSIZE)
        if self._stream_enabled:
            self._start_streaming(samplerate)
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="data discontinuity in recording",
                    category=getattr(sc, "SoundcardRuntimeWarning", Warning),
                )
                with mic_dev.recorder(samplerate=samplerate, blocksize=blocksize) as mic_rec, \
                        loopback_mic.recorder(samplerate=samplerate, blocksize=blocksize) as loop_rec:
                    block_count = 0
                    while self.is_recording:
                        if not self.is_recording:
                            break
                        mic_data = mic_rec.record(blocksize)
                        loop_data = loop_rec.record(blocksize)
                        self.mic_buffer.append(mic_data.copy())
                        self.loop_buffer.append(loop_data.copy())
                        if self._stream_enabled:
                            self._queue_stream_audio(mic_data, loop_data)
                        if block_count % 3 == 0:
                            mic_rms = float(np.sqrt(np.mean(np.square(mic_data))))
                            loop_rms = float(np.sqrt(np.mean(np.square(loop_data))))
                            self.root.after(0, self._update_levels, mic_rms, loop_rms)
                        block_count += 1
        except Exception as e:  # noqa: BLE001
            err_msg = str(e)
            self.root.after(0, lambda m=err_msg: messagebox.showerror("Fehler", f"Aufnahme fehlgeschlagen:\n{m}"))
        finally:
            self.is_recording = False
            self._stop_streaming()
            self.root.after(0, self._finish_recording)

    def _update_levels(self, mic_rms: float, loop_rms: float) -> None:
        mic_db = 20.0 * np.log10(max(mic_rms, 1e-8))
        loop_db = 20.0 * np.log10(max(loop_rms, 1e-8))
        self.mic_level_var.set(f"{mic_db:6.1f} dB")
        self.loop_level_var.set(f"{loop_db:6.1f} dB")
        self.mic_level_bar["value"] = self._db_to_percent(mic_db)
        self.loop_level_bar["value"] = self._db_to_percent(loop_db)

    def _db_to_percent(self, db_val: float) -> float:
        # Map [-60 dB .. 0 dB] -> [0 .. 100]
        if db_val <= -60.0:
            return 0.0
        if db_val >= 0.0:
            return 100.0
        return (db_val + 60.0) * (100.0 / 60.0)

    def _find_loopback_microphone(self, speaker_dev):
        try:
            mic = sc.get_microphone(speaker_dev.name, include_loopback=True)
            if mic is not None:
                return mic
        except Exception:  # noqa: BLE001
            mic = None

        try:
            all_mics = sc.all_microphones(include_loopback=True)
        except Exception:  # noqa: BLE001
            return None

        speaker_name = speaker_dev.name.lower()
        for m in all_mics:
            name = m.name.lower()
            if speaker_name in name and ("loopback" in name or "loop-back" in name):
                return m

        for m in all_mics:
            name = m.name.lower()
            if "loopback" in name or "loop-back" in name:
                return m

        return None

    def _start_streaming(self, samplerate: int) -> None:
        if not self._stream_url:
            self.root.after(0, lambda: self.status_var.set("Whisper Server URL fehlt."))
            self._stream_enabled = False
            return
        window_sec = max(0.1, float(self._stream_window_sec))
        overlap_sec = max(0.0, float(self._stream_overlap_sec))
        if overlap_sec >= window_sec:
            overlap_sec = max(0.0, window_sec - 0.5)
            self.root.after(0, lambda: self.status_var.set("Ueberlappung muss kleiner als Window sein."))
        if window_sec < 4.0:
            window_sec = 4.0
        if window_sec > 6.0:
            window_sec = 6.0
        self._stream_window_sec = window_sec
        self._stream_overlap_sec = overlap_sec
        self._stream_input_rate = samplerate
        self._stream_stop = threading.Event()
        self._stream_queue = queue.Queue(maxsize=6)
        self._stream_buffer = None
        self._stream_window_frames = max(1, int(round(samplerate * window_sec)))
        self._stream_overlap_frames = max(0, int(round(samplerate * overlap_sec)))
        self._stream_hop_frames = max(1, self._stream_window_frames - self._stream_overlap_frames)
        self._last_window_tokens = []
        self._stream_thread = threading.Thread(target=self._stream_worker, daemon=True)
        self._stream_thread.start()
        self.root.after(0, lambda: self.status_var.set("Streaming aktiv..."))

    def _stop_streaming(self) -> None:
        if self._stream_stop is None:
            return
        self._stream_stop.set()
        if self._stream_queue is not None:
            try:
                self._stream_queue.put_nowait(None)
            except Exception:  # noqa: BLE001
                pass
        if self._stream_thread is not None:
            self._stream_thread.join(timeout=2.0)
        self._stream_queue = None
        self._stream_thread = None
        self._stream_stop = None
        self._stream_buffer = None
        self._stream_window_frames = 0
        self._stream_overlap_frames = 0
        self._stream_hop_frames = 0
        self._last_window_tokens = []

    def _queue_stream_audio(self, mic_data: np.ndarray, loop_data: np.ndarray) -> None:
        if self._stream_stop is None or self._stream_stop.is_set():
            return
        source = mic_data
        if self._stream_source.lower().startswith("system"):
            source = loop_data
        elif self._stream_source.lower().startswith("mix"):
            if mic_data.shape == loop_data.shape:
                source = (mic_data + loop_data) * 0.5
            else:
                source = mic_data

        mono = self._to_mono(source)
        if self._stream_buffer is None or len(self._stream_buffer) == 0:
            self._stream_buffer = mono.copy()
        else:
            self._stream_buffer = np.concatenate([self._stream_buffer, mono], axis=0)
        while (
            self._stream_window_frames > 0
            and len(self._stream_buffer) >= self._stream_window_frames
        ):
            window = self._stream_buffer[:self._stream_window_frames].copy()
            self._stream_buffer = self._stream_buffer[self._stream_hop_frames:]
            if self._stream_queue is None:
                return
            try:
                self._stream_queue.put_nowait(window)
            except queue.Full:
                break

    def _stream_worker(self) -> None:
        while self._stream_stop is not None and not self._stream_stop.is_set():
            try:
                chunk = self._stream_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if chunk is None:
                break
            try:
                text = self._send_chunk_to_whisper(chunk)
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                self.root.after(0, lambda m=msg: self.status_var.set(f"Streaming-Fehler: {m}"))
                continue
            if text:
                self.root.after(0, self._handle_stream_text, text)

    def _send_chunk_to_whisper(self, chunk: np.ndarray) -> str:
        url = self._normalize_url(self._stream_url)
        wav_bytes = self._chunk_to_wav_bytes(chunk, self._stream_input_rate)
        fields = {}
        if self._stream_language:
            fields["language"] = self._stream_language
        fields["task"] = "translate" if self._stream_translate else "transcribe"
        body, content_type = self._build_multipart_form(fields, "file", "chunk.wav", wav_bytes, "audio/wav")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", content_type)
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
        return self._extract_text_from_response(raw)

    def _normalize_url(self, url: str) -> str:
        url = url.strip()
        if not url:
            raise ValueError("Whisper Server URL fehlt.")
        if "://" not in url:
            url = "http://" + url
        return url

    def _chunk_to_wav_bytes(self, chunk: np.ndarray, samplerate: int) -> bytes:
        mono = self._to_mono(chunk)
        resampled = self._resample_linear(mono, samplerate, STREAM_TARGET_SR)
        pcm = np.clip(resampled, -1.0, 1.0)
        buf = io.BytesIO()
        sf.write(buf, pcm, STREAM_TARGET_SR, subtype="PCM_16", format="WAV")
        return buf.getvalue()

    def _to_mono(self, data: np.ndarray) -> np.ndarray:
        if data.ndim > 1 and data.shape[1] > 1:
            mono = np.mean(data, axis=1)
        else:
            mono = data.reshape(-1)
        return mono.astype(np.float32, copy=False)

    def _resample_linear(self, data: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
        if src_rate == dst_rate:
            return data.astype(np.float32, copy=False)
        if len(data) < 2:
            return np.zeros(int(len(data) * dst_rate / max(src_rate, 1)), dtype=np.float32)
        src_len = len(data)
        dst_len = max(1, int(round(src_len * dst_rate / src_rate)))
        src_idx = np.linspace(0, src_len - 1, num=src_len, dtype=np.float32)
        dst_idx = np.linspace(0, src_len - 1, num=dst_len, dtype=np.float32)
        return np.interp(dst_idx, src_idx, data).astype(np.float32)

    def _build_multipart_form(
        self,
        fields: dict,
        file_field: str,
        filename: str,
        file_bytes: bytes,
        mime_type: str,
    ) -> tuple[bytes, str]:
        boundary = "----listenooga-" + datetime.now().strftime("%Y%m%d%H%M%S%f")
        lines = []
        for key, value in fields.items():
            lines.append(f"--{boundary}")
            lines.append(f'Content-Disposition: form-data; name="{key}"')
            lines.append("")
            lines.append(str(value))
        lines.append(f"--{boundary}")
        lines.append(f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"')
        lines.append(f"Content-Type: {mime_type}")
        lines.append("")
        body = "\r\n".join(lines).encode("utf-8") + b"\r\n" + file_bytes + b"\r\n"
        body += f"--{boundary}--\r\n".encode("utf-8")
        return body, f"multipart/form-data; boundary={boundary}"

    def _extract_text_from_response(self, raw: bytes) -> str:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:  # noqa: BLE001
            return ""
        if isinstance(payload, dict):
            if "text" in payload and isinstance(payload["text"], str):
                return payload["text"].strip()
            if "segments" in payload and isinstance(payload["segments"], list):
                parts = []
                for seg in payload["segments"]:
                    text = seg.get("text") if isinstance(seg, dict) else None
                    if text:
                        parts.append(text.strip())
                return " ".join(parts).strip()
        return ""

    def _handle_stream_text(self, text: str) -> None:
        if not text:
            return
        new_tokens = self._split_tokens(text)
        if not new_tokens:
            return
        if not self._transcript_tokens:
            self._transcript_tokens = list(new_tokens)
            self._last_window_tokens = list(new_tokens)
        elif not self._last_window_tokens:
            self._transcript_tokens.extend(new_tokens)
            self._last_window_tokens = list(new_tokens)
        else:
            merged_window = self._merge_window_tokens(self._last_window_tokens, new_tokens)
            if self._last_window_tokens:
                trim_len = min(len(self._transcript_tokens), len(self._last_window_tokens))
                if trim_len > 0:
                    self._transcript_tokens = self._transcript_tokens[:-trim_len]
            self._transcript_tokens.extend(merged_window)
            self._last_window_tokens = list(merged_window)
        self._transcript_tokens = self._dedupe_tail(self._transcript_tokens)
        self._set_transcript_text(" ".join(self._transcript_tokens))

    def _set_transcript_text(self, text: str) -> None:
        self.transcript_box.configure(state="normal")
        self.transcript_box.delete("1.0", "end")
        self.transcript_box.insert("end", text + " ")
        self.transcript_box.see("end")
        self.transcript_box.configure(state="disabled")

    def _split_tokens(self, text: str) -> list[str]:
        return [t for t in text.strip().split() if t]

    def _norm_token(self, token: str) -> str:
        return token.strip().lower().strip(".,!?;:\"'()[]{}")

    def _merge_window_tokens(self, prev_tokens: list[str], new_tokens: list[str]) -> list[str]:
        if not prev_tokens:
            return list(new_tokens)
        if not new_tokens:
            return list(prev_tokens)
        max_overlap = min(len(prev_tokens), len(new_tokens), 120)
        prev_norm = [self._norm_token(t) for t in prev_tokens]
        new_norm = [self._norm_token(t) for t in new_tokens]
        for k in range(max_overlap, 0, -1):
            if prev_norm[-k:] == new_norm[:k]:
                return list(prev_tokens) + list(new_tokens[k:])
        matcher = difflib.SequenceMatcher(None, prev_norm, new_norm, autojunk=False)
        best = 0
        for block in matcher.get_matching_blocks():
            if block.size < 3:
                continue
            if block.a + block.size == len(prev_norm) and block.b <= 3:
                if block.size > best:
                    best = block.size
        if best > 0:
            return list(prev_tokens) + list(new_tokens[best:])
        for k in range(max_overlap, 2, -1):
            prev_slice = prev_norm[-k:]
            new_slice = new_norm[:k]
            ratio = difflib.SequenceMatcher(None, prev_slice, new_slice, autojunk=False).ratio()
            if ratio >= 0.8:
                return list(prev_tokens) + list(new_tokens[k:])
        return list(prev_tokens) + list(new_tokens)

    def _dedupe_tail(self, tokens: list[str]) -> list[str]:
        if len(tokens) < 6:
            return tokens
        max_len = min(30, len(tokens) // 2)
        norm = [self._norm_token(t) for t in tokens]
        for k in range(max_len, 2, -1):
            if norm[-2 * k : -k] == norm[-k:]:
                return tokens[:-k]
        return tokens

    def _clear_transcript(self) -> None:
        self.transcript_box.configure(state="normal")
        self.transcript_box.delete("1.0", "end")
        self.transcript_box.configure(state="disabled")
        self._transcript_tokens = []
        self._last_window_tokens = []

    def _finish_recording(self) -> None:
        self.start_btn["state"] = "normal"
        self.stop_btn["state"] = "disabled"
        self.refresh_btn["state"] = "normal"

        if not self.mic_buffer or not self.loop_buffer:
            self.status_var.set("Keine Daten aufgezeichnet.")
            return

        mic_data = np.concatenate(self.mic_buffer, axis=0)
        loop_data = np.concatenate(self.loop_buffer, axis=0)

        min_len = min(len(mic_data), len(loop_data))
        mic_data = mic_data[:min_len]
        loop_data = loop_data[:min_len]

        mic_gain = float(self.mic_gain_var.get() or 1.0)
        if mic_gain != 1.0:
            mic_data = np.clip(mic_data * mic_gain, -1.0, 1.0)

        multi = np.concatenate([mic_data, loop_data], axis=1)
        base_name = (self.filename_var.get() or "recording").strip()
        safe_base = "".join(c for c in base_name if c.isalnum() or c in ("-", "_"))
        if not safe_base:
            safe_base = "recording"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_base}_{timestamp}.wav"
        sf.write(filename, multi, SAMPLE_RATE)

        loop_rms = float(np.sqrt(np.mean(np.square(loop_data)))) if len(loop_data) else 0.0
        if loop_rms < 1e-4:
            self.status_var.set("Gespeichert, aber Systemaudio sehr leise/leer.")
        else:
            self.status_var.set(f"Gespeichert: {filename}")


def main() -> None:
    root = tk.Tk()
    app = ListenoogaApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
