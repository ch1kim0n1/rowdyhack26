"""Rebuild the owned premiere sequence: python ui-kit/film/build-scroll-frames.py.

Requires ffmpeg on PATH. No third-party imagery or network calls.
"""
import json
import subprocess
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
out = KIT / 'media' / 'scroll-frames'
out.mkdir(exist_ok=True)
subprocess.run([
    'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
    '-i', str(KIT / 'media' / 'film-960.mp4'),
    '-vf', 'fps=24,scale=960:-1', '-frames:v', '501',
    '-c:v', 'libwebp', '-quality', '78', '-compression_level', '5',
    '-start_number', '0', str(out / 'frame-%03d.webp'),
], check=True)
frames = sorted(out.glob('frame-*.webp'))
assert len(frames) == 501, f'Expected 501 frames, got {len(frames)}'
manifest = {'count': 501, 'fps': 24, 'width': 960, 'height': 540,
            'bytes': sum(p.stat().st_size for p in frames),
            'source': '../film-960.mp4', 'pattern': 'frame-%03d.webp'}
(out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest))
