"""Divergence View Counter

@author: Sonicaii
@version: 1.0.0

Inspiration and orignal code from https://github.com/journey-ad/Moe-Counter/
"""

from flask import Flask, Response
import sqlite3
import os
import base64
import mimetypes


__version__ = "1.0.0"

app = Flask(__name__)

tubes_path = os.path.join(os.path.dirname(__file__), "tubes")
tubes = {}

def convert_to_datauri(path):
    mime = mimetypes.guess_type(path)[0]
    with open(path, "rb") as file:
        base64_data = base64.b64encode(file.read()).decode("utf-8")
    return f"data:{mime};base64,{base64_data}"

def get_count_image(count, length=7, border_radius=15):
    count_array = str(count).zfill(length)
    x, y = 0, 0
    parts = ""

    for digit in count_array:
        width = tubes[digit]["width"]
        height = tubes[digit]["height"]
        data = tubes[digit]["data"]

        parts += f'\n<image x="{x}" y="0" width="{width}" height="{height}" xlink:href="{data}" />'
        x += width
        y = max(y, height)

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg width="{x}" height="{y}" version="1.1" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" style="image-rendering: pixelated; border-radius: {border_radius}px;">
<title>View Count</title>
<g>
{parts}
</g>
</svg>
'''

@app.route('/<string:key>')
def serve_count_image(key):
    with sqlite3.connect("counter.db") as conn:
        c = conn.cursor()
        c.execute("SELECT count FROM counts WHERE key = ?", (key,))
        result = c.fetchone()

        # Get count of key or create it if it didn't exist
        if result is None:
            c.execute("INSERT INTO counts (key, count) VALUES (?, ?)", (key, 0))
            count = 0
        else:
            count = result[0]

        # Increment counter
        count += 1
        c.execute("UPDATE counts SET count = ? WHERE key = ?", (count, key))
        c.close()

    svg = get_count_image(count)
    headers = {
        'Content-Type': 'image/svg+xml',
        'Cache-Control': 'max-age=0, no-cache, no-store, must-revalidate'
    }
    return Response(svg, headers=headers)


# Load tube images
for img in os.listdir(tubes_path):
    img_path = os.path.join(tubes_path, img)
    name = os.path.splitext(img)[0]
    width, height = 88, 255

    tubes[name] = {
        "width": width,
        "height": height,
        "data": convert_to_datauri(img_path)
    }

# Initialise database
with sqlite3.connect("counter.db") as conn:
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS counts (key TEXT PRIMARY KEY, count BIGINT NOT NULL)")
    c.close()


if __name__ == '__main__':
    app.run()
