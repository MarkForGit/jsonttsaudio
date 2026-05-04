import argparse
import json
import re
from pathlib import Path
from openai import OpenAI

from utils import (
    load_markdown,
    smart_split,
    interp_curve,
    save_wav
)
from tts_engine import tts_generate

client = OpenAI(base_url="https://api.qnaigc.com/v1")

# ==== LLM ====
def generate_curves(text):
    prompt = f"""
You are a cinematic speech engine.
Return STRICT JSON:
{{
  "emo_curve": [{{"t":0.0,"emo_alpha":0.5,"emo_vector":[0,0,0.3,0.3,0,0.5,0,0.4]}}],
  "prosody_curve": [{{"t":0.0,"speech_rate":1.0,"pause_ms":120}}],
  "beats": [],
  "spk_audio_prompt": "ref.wav"
}}
Text:
\"\"\"{text}\"\"\"
"""
    resp = client.chat.completions.create(
        model="deepseek/deepseek-v4-flash",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        # 国产 API 部分不支持 response_format，靠 prompt 约束 JSON 输出[cite: 5]
    )

    raw = resp.choices[0].message.content
    
    # FIX 1: Strip markdown code block wrappers to prevent JSONDecodeError
    match = re.search(r'```(?:json)?\s*(.*?)\s*```', raw, re.DOTALL | re.IGNORECASE)
    if match:
        raw = match.group(1).strip()
        
    return json.loads(raw)


# ==== STATE ====
class NarrativeState:
    def __init__(self):
        self.tension = 1.0
        self.pace = 1.0

    def update(self, beats):
        # FIX 3: Ensure beats is iterable even if passed as None
        for b in (beats or []):
            if b.get("type") == "climax":
                self.tension = min(2.0, self.tension * 1.2) 
                self.pace = max(0.5, self.pace * 0.9)
            elif b.get("type") == "release":
                self.tension = max(0.1, self.tension * 0.8)
                self.pace = min(1.5, self.pace * 1.05)


def fuse_curve(curve, state, is_prosody=False):
    out = []
    for p in curve:
        p = p.copy()
        if not is_prosody:
            calculated_alpha = p.get("emo_alpha", 1.0) * state.tension
            p["emo_alpha"] = min(1.0, max(0.0, calculated_alpha))
        else:
            p["speech_rate"] = p.get("speech_rate", 1.0) * state.pace
        out.append(p)
    return out


# ==== INDEX-TTS MAPPING & VALIDATION ====
def build_tts_payload(text, emo, pro):
    """Flattens the curves into the exact schema IndexTTS expects.[cite: 5]"""
    return {
        "text": text,
        "emo_vector": emo.get("emo_vector"),
        "emo_alpha": max(0.0, min(1.0, emo.get("emo_alpha", 1.0))),  # Clamp 0-1[cite: 5]
        "use_emo_text": False,  # Prevent unpredictable blending[cite: 5]
    }

def validate_payload(p):
    """Fails loudly if the payload breaks IndexTTS rules.[cite: 5]"""
    assert "text" in p

    if p.get("emo_vector"):
        assert len(p["emo_vector"]) == 8, "emo_vector must be length 8"
        assert all(0 <= x <= 1 for x in p["emo_vector"]), "emo_vector values must be 0-1"

    if "emo_alpha" in p:
        assert 0 <= p["emo_alpha"] <= 1, "emo_alpha must be between 0 and 1"


# ==== MAIN PIPELINE ====
def run(input_path, output_path):
    paragraphs = load_markdown(input_path)

    state = NarrativeState()
    final_audio = []

    for para in paragraphs:
        data = generate_curves(para)

        # FIX 3: Safe get, protects against LLM returning "beats": null
        state.update(data.get("beats") or [])

        # FIX 2: Protect against KeyError with safe gets and fallback dummy curves
        default_emo = [{"t": 0.0, "emo_alpha": 1.0, "emo_vector": [0]*8}]
        default_pro = [{"t": 0.0, "speech_rate": 1.0, "pause_ms": 120}]
        
        emo_data = data.get("emo_curve") or default_emo
        pro_data = data.get("prosody_curve") or default_pro

        emo_curve = fuse_curve(emo_data, state)
        pro_curve = fuse_curve(pro_data, state, is_prosody=True)

        audio_prompt = data.get("spk_audio_prompt", "ref.wav")

        chunks = smart_split(para)

        for i, chunk in enumerate(chunks):
            
            if len(chunks) == 1:
                t = 0.5 
            else:
                t = i / (len(chunks) - 1)

            emo = interp_curve(emo_curve, t)
            pro = interp_curve(pro_curve, t)

            chunk_text = chunk  # emphasis removed: IndexTTS does not process text markers[cite: 5]

            # 1. Build strict IndexTTS Payload[cite: 5]
            payload = build_tts_payload(chunk_text, emo, pro)

            # 2. Validate before inference to catch silent failures[cite: 5]
            validate_payload(payload)

            # 3. Compute speed from prosody (applied as post-process time-stretch via librosa)[cite: 5]
            speed = max(0.5, min(1.5, pro.get("speech_rate", 1.0)))

            # 4. Execute TTS — speed is NOT passed to IndexTTS, applied post-hoc[cite: 5]
            audio = tts_generate(
                text=payload["text"],
                emo_vector=payload["emo_vector"],
                emo_alpha=payload["emo_alpha"],
                use_emo_text=payload["use_emo_text"],
                speed=speed,
                audio_prompt=audio_prompt
            )

            final_audio.append(audio)

    save_wav(final_audio, output_path)


# ==== CLI ====
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="Input markdown file")
    parser.add_argument("-o", "--output", default="narrated.wav")

    args = parser.parse_args()

    run(args.input, args.output)