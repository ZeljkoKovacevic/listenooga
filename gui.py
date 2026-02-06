import threading
import warnings
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox

import numpy as np
import soundcard as sc
import soundfile as sf


SAMPLE_RATE = 48000
BLOCKSIZE = 4096


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

        # Duration
        ttk.Label(main, text="Dauer (Sekunden):").grid(row=3, column=0, sticky="w")
        self.duration_var = tk.IntVar(value=20)
        self.duration_spin = ttk.Spinbox(main, from_=1, to=600, textvariable=self.duration_var, width=10)
        self.duration_spin.grid(row=3, column=1, sticky="w", pady=2)

        ttk.Label(main, text="Dateiname:").grid(row=4, column=0, sticky="w")
        self.filename_var = tk.StringVar(value="recording")
        self.filename_entry = ttk.Entry(main, textvariable=self.filename_var, width=30)
        self.filename_entry.grid(row=4, column=1, sticky="w", pady=2)

        ttk.Label(main, text="Samplerate:").grid(row=5, column=0, sticky="w")
        self.samplerate_var = tk.IntVar(value=SAMPLE_RATE)
        self.samplerate_spin = ttk.Spinbox(
            main,
            values=(22050, 44100, 48000),
            textvariable=self.samplerate_var,
            width=10,
            state="readonly",
        )
        self.samplerate_spin.grid(row=5, column=1, sticky="w", pady=2)

        ttk.Label(main, text="Blocksize:").grid(row=6, column=0, sticky="w")
        self.blocksize_var = tk.IntVar(value=BLOCKSIZE)
        self.blocksize_spin = ttk.Spinbox(
            main,
            values=(512, 1024, 2048, 4096, 8192),
            textvariable=self.blocksize_var,
            width=10,
            state="readonly",
        )
        self.blocksize_spin.grid(row=6, column=1, sticky="w", pady=2)

        ttk.Label(main, text="Mic-Gain (x):").grid(row=7, column=0, sticky="w")
        self.mic_gain_var = tk.DoubleVar(value=50.0)
        self.mic_gain_spin = ttk.Spinbox(
            main,
            from_=0.1,
            to=100.0,
            increment=5.0,
            textvariable=self.mic_gain_var,
            width=10,
        )
        self.mic_gain_spin.grid(row=7, column=1, sticky="w", pady=2)

        ttk.Label(main, text="Mic-Pegel:").grid(row=8, column=0, sticky="w")
        self.mic_level_var = tk.StringVar(value="--")
        self.mic_level_label = ttk.Label(main, textvariable=self.mic_level_var)
        self.mic_level_label.grid(row=8, column=1, sticky="w", pady=2)
        self.mic_level_bar = ttk.Progressbar(
            main,
            length=240,
            mode="determinate",
            maximum=100.0,
            style="Mic.Horizontal.TProgressbar",
        )
        self.mic_level_bar.grid(row=8, column=1, sticky="e", padx=5)

        ttk.Label(main, text="System-Pegel:").grid(row=9, column=0, sticky="w")
        self.loop_level_var = tk.StringVar(value="--")
        self.loop_level_label = ttk.Label(main, textvariable=self.loop_level_var)
        self.loop_level_label.grid(row=9, column=1, sticky="w", pady=2)
        self.loop_level_bar = ttk.Progressbar(
            main,
            length=240,
            mode="determinate",
            maximum=100.0,
            style="Sys.Horizontal.TProgressbar",
        )
        self.loop_level_bar.grid(row=9, column=1, sticky="e", padx=5)

        # Buttons
        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=10, column=0, columnspan=2, pady=10, sticky="ew")

        self.refresh_btn = ttk.Button(btn_frame, text="Devices neu laden", command=self._load_devices)
        self.refresh_btn.grid(row=0, column=0, padx=5)

        self.start_btn = ttk.Button(btn_frame, text="Aufnahme starten", command=self.start_recording)
        self.start_btn.grid(row=0, column=1, padx=5)

        self.stop_btn = ttk.Button(btn_frame, text="Stop", command=self.stop_recording, state="disabled")
        self.stop_btn.grid(row=0, column=2, padx=5)

        # Status
        self.status_var = tk.StringVar(value="Bereit.")
        self.status_label = ttk.Label(main, textvariable=self.status_var)
        self.status_label.grid(row=11, column=0, columnspan=2, sticky="w", pady=5)

        main.columnconfigure(1, weight=1)

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

        duration = self.duration_var.get()
        if duration <= 0:
            messagebox.showwarning("Hinweis", "Dauer muss > 0 sein.")
            return

        self.is_recording = True
        self.mic_buffer.clear()
        self.loop_buffer.clear()

        self.start_btn["state"] = "disabled"
        self.stop_btn["state"] = "normal"
        self.refresh_btn["state"] = "disabled"
        self.status_var.set("Aufnahme laeuft...")

        threading.Thread(
            target=self._record_worker,
            args=(mic_idx, out_idx, duration),
            daemon=True,
        ).start()

    def stop_recording(self) -> None:
        if not self.is_recording:
            return
        self.is_recording = False
        self.status_var.set("Stop angefordert...")

    def _record_worker(self, mic_idx: int, out_idx: int, duration: int) -> None:
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
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="data discontinuity in recording",
                    category=getattr(sc, "SoundcardRuntimeWarning", Warning),
                )
                with mic_dev.recorder(samplerate=samplerate, blocksize=blocksize) as mic_rec, \
                        loopback_mic.recorder(samplerate=samplerate, blocksize=blocksize) as loop_rec:
                    total_blocks = int(duration * samplerate / blocksize)
                    for i in range(total_blocks):
                        if not self.is_recording:
                            break
                        mic_data = mic_rec.record(blocksize)
                        loop_data = loop_rec.record(blocksize)
                        self.mic_buffer.append(mic_data.copy())
                        self.loop_buffer.append(loop_data.copy())
                        if i % 3 == 0:
                            mic_rms = float(np.sqrt(np.mean(np.square(mic_data))))
                            loop_rms = float(np.sqrt(np.mean(np.square(loop_data))))
                            self.root.after(0, self._update_levels, mic_rms, loop_rms)
        except Exception as e:  # noqa: BLE001
            err_msg = str(e)
            self.root.after(0, lambda m=err_msg: messagebox.showerror("Fehler", f"Aufnahme fehlgeschlagen:\n{m}"))
        finally:
            self.is_recording = False
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
