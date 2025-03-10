"""Divergence View Renderer Server

@author: Sonicaii
: 0.3.2

    TODO:
        - Caching system, Regenerate commonly requested numbers
        - Request server
"""
import logging
import os
import random
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import bpy
from dotenv import load_dotenv

__version__ = "0.3.2"

from flask import Flask, abort, send_file

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("render")

DIGITS = 8

SAMPLES = int(os.environ.get("RENDER_SAMPLES", 4096))
DEVICE_TYPE = os.environ.get("RENDER_DEVICE_TYPE", "OPTIX")
TOTAL_FRAMES = int(os.environ.get("RENDER_TOTAL_FRAMES", 60))
EXPORT_GIF_WIDTH = str(os.environ.get("EXPORT_GIF_WIDTH", 1500))
BLEND_FILE_PATH = os.environ.get("BLEND_FILE_PATH", "./blender/tubes.blend")
RENDER_OUTPUT_DIR = os.environ.get("RENDER_OUTPUT_DIR", "./blender/output")
CACHE_DIR = os.environ.get("CACHE_DIR", "./cache")


@dataclass
class Chances:
    """Constants determining tube flickering animation probabilities and duration"""
    START = 0.01
    SKIP_DIM = 0.5
    DURATION_MIN = 0
    DURATION_MAX = 5


class Renderer:
    def __init__(self, blend_file_path=BLEND_FILE_PATH,
                 on_material_name="number_on_mt",
                 off_material_name="number_off_mt",
                 half_material_name="number_half_mt",
                 total_frames=60,
                 chances=None):
        self.logger = logger

        bpy.ops.wm.open_mainfile(filepath=blend_file_path)
        self.logger.info(f"Successfully loaded {blend_file_path}")

        # Get material references
        self.on_mat = bpy.data.materials.get(on_material_name)
        self.off_mat = bpy.data.materials.get(off_material_name)
        self.half_mat = bpy.data.materials.get(half_material_name)

        self.total_frames = total_frames

        # Update with any custom values
        self.chances = Chances()
        for k, v in ({} if chances is None else chances).items():
            self.chances.k = v

        if not all([self.on_mat, self.off_mat, self.half_mat]):
            self.logger.warning(f"Available materials:")
            for mat in bpy.data.materials:
                self.logger.warning(f"  - {mat.name}")
            raise ValueError("Materials not found.")

        # Set up tubes mesh lookup, navigating through object structure
        # _tubes is a 2D list of tubes (lists of length DIGITS) that holds 10 filaments (bpy.types.Object)
        self._tubes = []
        for tube in sorted([o for o in bpy.data.objects if o.name.startswith("display")], key=lambda o: o.name):
            number_objs = [child for child in tube.children if child.name.startswith("number")]

            if not number_objs:
                raise ValueError(f"No number objects found under {tube.name}")

            filaments = [child for child in number_objs[0].children
                         if child.name.startswith("num") and not child.name.startswith("numDot")]

            meshes = []
            for filament in filaments:
                mesh_children = [child for child in filament.children if child.type == "MESH"]

                if not mesh_children:
                    raise ValueError(f"No mesh children found for {filament.name}")

                meshes.append(mesh_children[0])

            self._tubes.append(meshes)

        # Blender settings
        bpy.context.scene.render.engine = "CYCLES"

        # Enable GPU rendering
        if DEVICE_TYPE:
            cycles_prefs = bpy.context.preferences.addons["cycles"].preferences
            cycles_prefs.compute_device_type = DEVICE_TYPE
            cycles_prefs.get_devices()  # Refresh device list

            active_devices = []

            for device in cycles_prefs.devices:
                if "CPU" not in device.name:  # Ignore CPU devices
                    device.use = True
                    active_devices.append(f"{device.name} ({device.type})")
                else:
                    device.use = False  # Ensure CPU is disabled

            # Set rendering to use GPU
            bpy.context.scene.cycles.device = "GPU"

            # Log active devices
            self.logger.debug(f"Enabled GPU devices: {', '.join(active_devices)}")

        bpy.context.scene.cycles.samples = SAMPLES
        self.logger.info(
            f"Set render engine to {bpy.context.scene.render.engine} and device type to " +
            bpy.context.preferences.addons["cycles"].preferences.compute_device_type
        )

    def set_display_number(self, number: int | str, state: list = None):
        """Iterates through all tubes' meshes and toggles filaments to match. Non digit character = Tube off"""
        if isinstance(number, int):
            number = str(number).zfill(DIGITS)
        if len(number) > DIGITS:
            raise ValueError(f"{number} has more than {DIGITS} digits!")

        if state is None:
            state = [self.on_mat] * DIGITS
        if len(state) != DIGITS:
            raise ValueError(f"{state} must be {DIGITS} long")

        state_str = "".join([{self.on_mat: "█", self.half_mat: "░", self.off_mat: "_"}[s] for s in state])
        self.logger.info(f"Setting tubes:  {number}")
        self.logger.info(f"Setting states: {state_str}")

        for tube, digit in enumerate(number):
            for i, filament in enumerate(self._tubes[tube]):
                if str(i) == digit:
                    filament.material_slots[0].material = state[tube]
                else:
                    filament.material_slots[0].material = self.off_mat
                self.logger.debug(f"Set {filament.name} (digit {i}) to {filament.material_slots[0].material}")

        bpy.context.view_layer.update()
        return True

    def render_frame(self, output: Path, frame=1):
        output.parent.mkdir(parents=True, exist_ok=True)

        bpy.context.scene.frame_set(frame)
        bpy.context.scene.render.filepath = str(output)

        self.logger.info(f"Rendering frame to {output}")
        self.logger.debug(f"Res: {bpy.context.scene.render.resolution_x}x{bpy.context.scene.render.resolution_y}")

        bpy.ops.render.render(write_still=True)

        self.logger.info(f"Rendering complete: {output}")
        return output

    def animate_display(self, number: int, output_dir=RENDER_OUTPUT_DIR):
        """Generates an animation with flickering tubes"""
        start = time.perf_counter()
        state = [self.on_mat] * DIGITS
        durations = [0] * DIGITS  # Number of frames tube is off

        with tempfile.TemporaryDirectory() as tmp_folder:
            tmp_folder = Path(tmp_folder)
            for frame in range(1, self.total_frames + 1):

                # Apply flickering logic per tube
                for i in range(DIGITS):

                    if durations[i]:
                        durations[i] -= 1
                        state[i] = self.off_mat
                        if durations[i] and random.random() < self.chances.SKIP_DIM:  # Next frame it will reactivate
                            # Start to reactivate material with dim
                            state[i] = self.half_mat
                    else:
                        state[i] = self.on_mat

                    neighbour_active = durations[(i - 1) % DIGITS] or durations[(i + 1) % DIGITS]
                    if random.random() < self.chances.START and not neighbour_active:
                        if random.random() < self.chances.SKIP_DIM:
                            state[i] = self.half_mat
                        durations[i] = random.randint(self.chances.DURATION_MIN, self.chances.DURATION_MAX)

                self.set_display_number(number, state)
                self.render_frame(tmp_folder / f"{frame}.png", frame)

            self.logger.info("All frames rendered.")

            command = [
                "ffmpeg",
                "-framerate", "60",
                "-i", str(tmp_folder / "%d.png"),
                "-vf", f"scale={EXPORT_GIF_WIDTH}:-1:flags=lanczos",
                "-r", "60",
                "-y", f"{number}.gif"
            ]

            subprocess.run(command, cwd=output_dir, check=True)
            self.logger.info(
                "Exported as %s.gif in %.2f seconds",
                Path(output_dir) / str(number),
                round(time.perf_counter() - start, 2)
            )


app = Flask(__name__)


@app.route("/<int:number>")
def serve_gif(number):
    source_path = os.path.join(RENDER_OUTPUT_DIR, f"{number}.gif")
    cache_path = os.path.join(CACHE_DIR, f"{number}.gif")

    # Update cache with new version
    if os.path.exists(source_path):
        shutil.move(source_path, cache_path)

    if not os.path.exists(cache_path):
        abort(404, "GIF not found")

    return send_file(cache_path, mimetype="image/gif")


if __name__ == "__main__":
    try:
        app.renderer = Renderer(total_frames=TOTAL_FRAMES)
    except Exception as e:
        logger.error(f"Error loading blend file: {e}")
        exit(1)

    # app.run(host="0.0.0.0", port=5000)

    app.renderer.animate_display(0)
