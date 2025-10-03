
import os
import time
import tkinter as tk
from tkinter import filedialog

# Hidden tkinter interface as we use it only for filedialog
root = tk.Tk()
root.withdraw()

# Custom configuration for OpenAL, disabling HRTF Filter
os.environ["ALSOFT_CONF"] = "alsoft.ini"

import glux
from glux import imgui

import moderngl as mgl
import numpy as np

# Shader loading utility
def load_shader(filename: str):
    data = None
    with open(filename, 'r') as f:
        data = f.read()
    return data

# Applies FFT to given chunk and returns the spectrum and freqs
def compute_spectrum(chunk, sample_rate):
    # Apply a window function to reduce noise
    window = np.hanning(len(chunk))
    chunk = chunk * window

    # FFT
    spectrum = np.fft.fft(chunk)
    spectrum = np.abs(spectrum)

    # Keep only first half (real frequencies)
    spectrum = spectrum[:len(spectrum)//2]

    freqs = np.fft.fftfreq(len(chunk), d=1/sample_rate)
    freqs = freqs[:len(freqs)//2]

    return freqs, spectrum

# Converts the spectrum into logarithmically-spaced bars
def make_bars(spectrum, freqs, num_bars=64):
    bars = []
    min_freq, max_freq = 20, 20000
    log_min, log_max = np.log10(min_freq), np.log10(max_freq)
    log_bins = np.logspace(log_min, log_max, num_bars+1, base=10)

    for i in range(num_bars):
        f1, f2 = log_bins[i], log_bins[i+1]
        mask = (freqs >= f1) & (freqs < f2)
        if np.any(mask):
            # Represent as an average of amplitudes in the range mask
            bars.append(spectrum[mask].mean())
        else:
            bars.append(0)
    return np.array(bars)


class App:

    # Program container

    def __init__(self, width, height, title):
        self.window = glux.Window(width, height, title)
        self.window.set_process_callback(self.process)
        self.window.set_render_callback(self.render)
        self.window.set_render_ui_callback(self.render_ui)

        self.init_time = time.time()

        self.oal_ctx = glux.oal.Context()
        self.ctx = mgl.create_context()
        self.ctx.line_width = 3
        imgui.get_io().font_global_scale = 2.0

        # Reserve bytes to be overwritten later
        self.vbo = self.ctx.buffer(reserve=2 * 4 * 2 * 4 * 64)
        self.program = self.ctx.program(load_shader("vert.glsl"), load_shader("frag.glsl"))
        self.vao = self.ctx.vertex_array(self.program, self.vbo, 'in_pos')

        self.filename = ""

        self.music_data = None
        self.n_channels = 0
        self.sample_width = 0
        self.frame_rate = 0
        self.n_frames = 0
        self.raw_data = 0
        self.duration = 0
        self.bytes_per_sample = 0
        self.bar_max = 1

        # Number of samples we see from the start point i.e. sliding window size
        self.frame_size = 4096

        self.stream = self.oal_ctx.create_stream()
        self.stream_offset = 0

    def load_file(self):
        file_path = filedialog.askopenfilename(
                        title="Select a file",
                        filetypes=[("Audio files", ["*.mp3", ".ogg", ".wav"])]
                        )
        if file_path and not self.filename == str(file_path):
            self.filename = str(file_path)
            self.music_data = self.oal_ctx.decode_file(self.filename)
            self.n_channels = self.music_data.channels
            self.sample_width = self.music_data.bits_per_sample // 8
            self.frame_rate = self.music_data.sample_rate
            self.n_frames = self.music_data.n_samples()
            self.raw_data = self.music_data.raw_data()
            self.duration = self.music_data.duration()
            self.bytes_per_sample = self.n_channels * self.sample_width
            self.bar_max = 1
            return True
        return False

    def process(self):
        self.program["time"] = time.time() - self.init_time
        if self.stream.is_playing():
            self.stream.update()
        self.stream_offset = self.stream.get_offset_seconds()

        if self.stream_offset:
            # Get index of starting sample point
            sample_index = int(self.stream_offset * self.frame_rate) % self.n_frames
            
            # Sample index --> bytes from start
            start_byte = sample_index * self.bytes_per_sample

            # Start byte + bytes corresponding to frame size
            end_byte = start_byte + self.frame_size * self.bytes_per_sample

            # Get the slice of raw data we want to process
            raw_slice = self.raw_data[start_byte:end_byte]

            # Process the slice and ultimately get bars
            audio_data = np.frombuffer(raw_slice, dtype=np.int16)
            if self.n_channels == 2:
                audio_data = audio_data.reshape(-1, 2)
                audio_data = audio_data.mean(axis=1).astype(np.int16)

            chunk = audio_data
            freqs, spectrum = compute_spectrum(chunk, self.frame_rate)
            
            # bars: collection of mean amplitudes for each frequency subinterval
            bars = make_bars(spectrum, freqs)

            # Normalize bar heights based on the max bar size seen yet
            for i, bar in enumerate(bars):
                if bar > self.bar_max:
                    self.bar_max = bar

            data = []
            blanks = 0
            for i, bar in enumerate(bars):
                y = bar / self.bar_max
                if y > 0:
                    # Mirrored the Ist quadrant across X and Y axes
                    p = ((i - blanks) / 64, 0.5 * bar / self.bar_max)
                    data.extend([p[0], 0, p[0], p[1]])
                    p = ((i - blanks) / 64, -0.5 * bar / self.bar_max)
                    data.extend([p[0], 0, p[0], p[1]])
                    p = (-(i - blanks) / 64, 0.5 * bar / self.bar_max)
                    data.extend([p[0], 0, p[0], p[1]])
                    p = (-(i - blanks) / 64, -0.5 * bar / self.bar_max)
                    data.extend([p[0], 0, p[0], p[1]])
                else:
                    blanks += 1
            self.vertices = np.array(data, dtype = 'f4')
            self.vbo.write(self.vertices)

    def render(self):
        self.ctx.clear(0.0, 0.0, 0.0, 1.0)
        if self.stream_offset:
            self.vao.render(mgl.LINES)

    def render_ui(self):
        imgui.begin("Playback")
        if imgui.button("Load  "):
            self.stream.pause()
            loaded = self.load_file()
            if loaded :
                self.stream.stop()
            else:
                self.stream.resume()
        if imgui.button("Play  "):
            if self.filename:
                self.stream.play(self.filename, loop=True)
        if imgui.button("Pause "):
            if self.stream.is_playing():
                self.stream.pause()
        if imgui.button("Resume"):
            if self.stream.is_paused():
                self.stream.resume()
        if imgui.button("Stop  "):
            if self.stream.is_playing():
                self.stream.stop()
        imgui.end()

    def run(self):
        self.window.run()

app = App(1280, 720, "Audio Spectrum Visualizer")
app.run()