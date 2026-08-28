#!/usr/bin/env python3
"""segments.json + fa_cues.json -> fa.srt + fa.ass.
ASS times are H:MM:SS.CC (2-digit centis — 3-digit fraction poisons libass 0.15!).
Zero overlap enforced. Style constants (FontSize 19, MarginV 24) are tuned for
360p; for other resolutions scale: size=H*0.053, MarginV=H*0.067.
Usage: python make_ass.py <ws> <font> [width height]  (default 640 360)"""
import json, sys

WS, FONT = sys.argv[1], sys.argv[2]
W = int(sys.argv[3]) if len(sys.argv) > 3 else 640
H = int(sys.argv[4]) if len(sys.argv) > 4 else 360
FS = int(round(H * 0.053))     # ~19 @360p
MV = int(round(H * 0.067))     # ~24 @360p
segs = json.load(open(f"{WS}/segments.json", encoding="utf-8"))
fa = json.load(open(f"{WS}/fa_cues.json", encoding="utf-8"))

cues = []
for i, s in enumerate(segs):
    t = fa.get(str(i), "").strip()
    if not t: continue
    st, en = s["start"], s["end"]
    if i + 1 < len(segs): en = min(en, segs[i + 1]["start"])
    if en - st < 0.6: en = st + 0.6
    cues.append((st, en, t))

def ts(t):
    h = int(t // 3600); m = int(t % 3600 // 60); sec = t % 60
    return f"{h:02d}:{m:02d}:{sec:06.3f}".replace(".", ",")

def ts_ass(t):
    h = int(t // 3600); m = int(t % 3600 // 60); sec = int(t % 60)
    cs = int(round((t - int(t)) * 100)) % 100
    return f"{h:d}:{m:02d}:{sec:02d}.{cs:02d}"

with open(f"{WS}/fa.srt", "w", encoding="utf-8") as f:
    for i, (st, en, t) in enumerate(cues, 1):
        f.write(f"{i}\n{ts(st)} --> {ts(en)}\n{t}\n\n")

with open(f"{WS}/fa.ass", "w", encoding="utf-8") as f:
    f.write(f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{FONT},{FS},&H00FFFFFF,&H000000FF,&H00141414,&H64000000,1,0,0,0,100,100,0,0,1,1.5,0.6,2,24,24,{MV},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""")
    for i, (st, en, t) in enumerate(cues):
        t = t.replace("\n", " ").strip()
        f.write(f"Dialogue: 0,{ts_ass(st)},{ts_ass(en)},Default,,0,0,0,,{t}\n")
print(f"wrote {WS}/fa.srt ({len(cues)}) + fa.ass (font={FONT})")
