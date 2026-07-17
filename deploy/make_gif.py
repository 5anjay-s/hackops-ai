"""Convert demo.mp4 to a compressed GIF for GitHub README."""
from moviepy import VideoFileClip

clip = VideoFileClip("d:/hackops-ai/demo/demo.mp4")

# Aggressive compression: 480px width, 5fps, 20s max
clip_resized = clip.resized(width=480)
clip_resized = clip_resized.with_fps(5)

# Cap at 20 seconds
if clip.duration > 20:
    clip_resized = clip_resized.subclipped(0, 20)

clip_resized.write_gif("d:/hackops-ai/demo/demo.gif")
print(f"GIF created! Duration: {clip_resized.duration:.1f}s")

import os
size = os.path.getsize("d:/hackops-ai/demo/demo.gif") / 1024 / 1024
print(f"Size: {size:.2f} MB")
