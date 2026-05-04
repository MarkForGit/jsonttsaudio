import re
import numpy as np
import soundfile as sf


def load_markdown(path):
    text = open(path, encoding="utf-8").read()

    text = re.sub(r'#.*', '', text)
    text = re.sub(r'\*+', '', text)
    text = re.sub(r'\[.*?\]\(.*?\)', '', text)

    return [p.strip() for p in text.split("\n\n") if p.strip()]


def smart_split(text):
    parts = re.split(r'(?<=[.!?]) +', text)

    out, buf = [], ""
    for p in parts:
        if len(buf) + len(p) < 120:
            buf += " " + p
        else:
            out.append(buf.strip())
            buf = p
    if buf:
        out.append(buf.strip())

    return out


def lerp(a, b, t):
    return a + (b - a) * t


def interp_curve(curve, t):
    for i in range(len(curve) - 1):
        if curve[i]["t"] <= t <= curve[i + 1]["t"]:
            t0, t1 = curve[i]["t"], curve[i + 1]["t"]
            w = (t - t0) / (t1 - t0)

            out = {}
            for k in curve[i]:
                if k == "t":
                    continue
                if isinstance(curve[i][k], list):
                    out[k] = [
                        lerp(curve[i][k][j], curve[i + 1][k][j], w)
                        for j in range(len(curve[i][k]))
                    ]
                else:
                    out[k] = lerp(curve[i][k], curve[i + 1][k], w)
            return out

    return curve[-1]


def apply_emphasis(text, level):
    if level > 0.7:
        return text.upper()
    elif level > 0.4:
        return text.replace(",", ", ...")
    return text


def save_wav(chunks, path):
    audio = np.concatenate(chunks)
    sf.write(path, audio, 24000)