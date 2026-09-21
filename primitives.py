# -*- coding: utf-8 -*-
"""
primitives.py — 8 种 primitive acoustic effects（论文附录 C.2 / Table 14）

每种 primitive 是一个独立的信号级变换，接口统一为：
    fn(wav: np.ndarray, sr: int, rng: np.random.Generator, **params) -> np.ndarray
约定：单声道 float32，值域 [-1, 1]；除 loudness 外均不改变长度。
"""
import numpy as np
from scipy import signal as sps

try:
    import pyloudnorm as pyln
    _METER = {}  # 按采样率缓存 BS.1770 meter

    def _lufs(wav, sr):
        meter = _METER.get(sr)
        if meter is None:
            meter = _METER[sr] = pyln.Meter(sr)
        # 极短/静音音频响度不可靠时返回 None（论文约定保持不变）
        if len(wav) < int(0.4 * sr) or np.max(np.abs(wav)) < 1e-6:
            return None
        try:
            return meter.integrated_loudness(wav.astype(np.float64))
        except Exception:
            return None

    def loudness_to(wav, sr, target_lufs):
        cur = _lufs(wav, sr)
        if cur is None or not np.isfinite(cur):
            return wav
        out = pyln.normalize.loudness(wav.astype(np.float64), cur, target_lufs)
        peak = np.max(np.abs(out))
        if peak > 1.0:  # 防爆音
            out = out / peak * 0.99
        return out.astype(np.float32)
except ImportError:  # 无 pyloudnorm 时退化为 RMS 归一化（粗略等价 -23 LUFS ≈ -23 dB RMS）
    def loudness_to(wav, sr, target_lufs):
        rms = np.sqrt(np.mean(wav**2)) + 1e-12
        target_rms = 10 ** (target_lufs / 20.0)
        out = wav * (target_rms / rms)
        peak = np.max(np.abs(out))
        if peak > 1.0:
            out = out / peak * 0.99
        return out.astype(np.float32)


# ---------------------------------------------------------------- 1. additive noise
def add_noise(wav, sr, rng, noise_db, noise_pool=None, use_white_noise=False, wet=1.0):
    """混入外部噪声。noise_db 为 SNR（语音相对噪声的 dB 差，越小越难）。
    noise_pool: NoisePool 实例；use_white_noise=True 时用白噪声（录音链）。"""
    if use_white_noise or noise_pool is None:
        noise = rng.standard_normal(len(wav)).astype(np.float32)
    else:
        noise = noise_pool.sample(len(wav), rng)
    speech_rms = np.sqrt(np.mean(wav**2)) + 1e-12
    noise_rms = np.sqrt(np.mean(noise**2)) + 1e-12
    scaled = noise * (speech_rms / (10 ** (noise_db / 20.0)) / noise_rms)
    out = (1.0 - wet) * wav + wet * (wav + scaled)
    return np.clip(out, -1.0, 1.0).astype(np.float32)


# ---------------------------------------------------------------- 2. echo delay
def add_echo(wav, sr, rng, delay_seconds, feedback, mix):
    """反馈梳状滤波：y[n] = x[n] + feedback * y[n-D]，再按 mix 干湿混合。"""
    d = max(1, int(delay_seconds * sr))
    b = np.zeros(d + 1, dtype=np.float64)
    b[0] = 1.0
    a = np.zeros(d + 1, dtype=np.float64)
    a[0] = 1.0
    a[d] = -float(feedback)
    wet_sig = sps.lfilter(b, a, wav)
    out = (1.0 - mix) * wav + mix * wet_sig
    peak = np.max(np.abs(out))
    if peak > 1.0:
        out = out / peak * 0.99
    return out.astype(np.float32)


# ---------------------------------------------------------------- 3. reverberation
def _synth_rir(sr, room_size, damping, rng):
    """指数衰减噪声 RIR。room_size∈[0,1] -> RT60∈[0.15, 2.0]s；damping 控制高频衰减。"""
    rt60 = 0.15 + (2.0 - 0.15) * float(room_size)
    n = max(int(rt60 * sr), 64)
    t = np.arange(n) / sr
    rir = rng.standard_normal(n) * np.exp(-6.91 * t / rt60)  # -60dB 衰减
    if damping > 0:
        cutoff = sr / 2 * (1.0 - 0.85 * float(damping))
        cutoff = max(500.0, min(cutoff, sr / 2 * 0.99))
        sos = sps.butter(2, cutoff, btype="lowpass", fs=sr, output="sos")
        rir = sps.sosfilt(sos, rir)
    rir[0] += 1.0  # 直达声
    return rir.astype(np.float32)


def add_reverb(wav, sr, rng, room_size, damping, wet_level, dry_level):
    """卷积混响（dense reflections），按 wet/dry 电平混合，输出裁回原长。"""
    rir = _synth_rir(sr, room_size, damping, rng)
    wet_sig = sps.fftconvolve(wav, rir)[: len(wav)]
    wet_sig /= (np.max(np.abs(wet_sig)) + 1e-12)
    wet_sig *= np.max(np.abs(wav)) + 1e-12
    out = float(dry_level) * wav + float(wet_level) * wet_sig
    peak = np.max(np.abs(out))
    if peak > 1.0:
        out = out / peak * 0.99
    return out.astype(np.float32)


# ---------------------------------------------------------------- 4. nonlinear distortion
def add_distortion(wav, sr, rng, drive_db, wet=1.0):
    """过载/削波：增益驱动 -> tanh 软饱和 -> 硬削波到 [-1,1]。"""
    drive = 10 ** (float(drive_db) / 20.0)
    driven = np.tanh(wav * drive)
    driven = np.clip(driven * 1.2, -1.0, 1.0)
    out = (1.0 - wet) * wav + wet * driven
    return np.clip(out, -1.0, 1.0).astype(np.float32)


# ---------------------------------------------------------------- 5. resampling
def add_resample(wav, sr, rng, target_sr, prob, threshold=0.4, wet=1.0):
    """先降到 target_sr 再升回原采样率，模拟带宽受限。
    概率门：严重度 prob < threshold 时不施加（论文 recording 链 threshold=0.4）。"""
    if prob < threshold:
        return wav
    g = np.gcd(sr, int(target_sr))
    down = sps.resample_poly(wav, int(target_sr) // g, sr // g)
    up = sps.resample_poly(down, sr // g, int(target_sr) // g)
    up = up[: len(wav)]
    if len(up) < len(wav):
        up = np.pad(up, (0, len(wav) - len(up)))
    out = (1.0 - wet) * wav + wet * up
    return out.astype(np.float32)


# ---------------------------------------------------------------- 6. spectral filtering
def apply_filter(wav, sr, rng, cutoff_hz, filter_type="lowpass", repeat=1, wet=1.0):
    """Butterworth 低通/高通，repeat 次级联增强衰减强度。"""
    nyq = sr / 2.0
    cutoff = min(max(float(cutoff_hz), 20.0), nyq * 0.99)
    sos = sps.butter(4, cutoff, btype=filter_type, fs=sr, output="sos")
    out = wav.astype(np.float64)
    for _ in range(int(repeat)):
        out = sps.sosfilt(sos, out)
    out = (1.0 - wet) * wav + wet * out
    return out.astype(np.float32)


# ---------------------------------------------------------------- 7. loudness transformation
def change_volume(wav, sr, rng, target_lufs):
    """LUFS 响度归一化（距离衰减 / 增益失配）。静音或过短音频保持原样。"""
    return loudness_to(wav, sr, float(target_lufs))


# ---------------------------------------------------------------- 8. frame-level stutter
def add_stutter_replace(wav, sr, rng, stutter_prob, repeat_prob, max_repeats, frame_ms=20):
    """20ms 帧级丢包：触发后以 repeat_prob 概率重复前一帧（至多 max_repeats 帧），
    否则置零（丢包）。总长不变，保持与转写对齐。"""
    fl = max(1, int(frame_ms * sr / 1000))
    n_frames = int(np.ceil(len(wav) / fl))
    out = wav.copy()
    i = 0
    while i < n_frames:
        if rng.random() < stutter_prob:
            k = int(rng.integers(1, int(max_repeats) + 1))
            if i > 0 and rng.random() < repeat_prob:
                prev = out[(i - 1) * fl: i * fl]
                for j in range(i, min(i + k, n_frames)):
                    out[j * fl: (j + 1) * fl] = prev[: len(out[j * fl: (j + 1) * fl])]
            else:
                for j in range(i, min(i + k, n_frames)):
                    out[j * fl: (j + 1) * fl] = 0.0
            i += k
        else:
            i += 1
    return out


PRIMITIVES = {
    "add_noise": add_noise,
    "add_echo": add_echo,
    "add_reverb": add_reverb,
    "add_distortion": add_distortion,
    "add_resample": add_resample,
    "apply_filter": apply_filter,
    "change_volume": change_volume,
    "add_stutter_replace": add_stutter_replace,
}
