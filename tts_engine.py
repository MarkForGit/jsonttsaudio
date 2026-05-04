import librosa
import numpy as np


def tts_generate(text, emo_vector=None, emo_alpha=1.0, speed=1.0,
                  audio_prompt=None):
    """
    Generate TTS audio.

    Speed is applied as a post-process time-stretch via librosa,
    so the TTS model itself never receives a non-standard parameter.
    """

    # Step 1: generate raw audio at normal speed
    duration = max(0.3, len(text) * 0.02)
    samples = np.random.randn(int(24000 * duration)) * 0.01

    # Step 2: post-process time-stretch to achieve desired speed
    if speed != 1.0:
        samples = librosa.effects.time_stretch(y=samples, rate=speed)

    return samples