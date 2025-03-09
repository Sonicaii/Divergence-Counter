"""Divergence View Renderer Server

@author: Sonicaii
@version: 0.3.0

    TODO:
        - Caching system, Regenerate commonly requested numbers
        - Automate deleting of png exports
        - Request server
"""
import logging
import os
import random
import subprocess
from dataclasses import dataclass
from pathlib import Path

import bpy
from dotenv import load_dotenv

__version__ = "0.2.0"

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


@dataclass
class Chances:
    START = 0.01
    SKIP_DIM = 0.5
    DURATION_MIN = 0
    DURATION_MAX = 5


SAMPLES = int(os.environ.get("RENDER_SAMPLES", 4096))
DEVICE_TYPE = os.environ.get("RENDER_DEVICE_TYPE")
TOTAL_FRAMES = int(os.environ.get("RENDER_TOTAL_FRAMES", 60))
EXPORT_GIF_WIDTH = str(os.environ.get("EXPORT_GIF_WIDTH", 1500))


class Renderer:
    def __init__(self, blend_file_path="blender/tubes.blend",
                 on_material_name="number_on_mt",
                 off_material_name="number_off_mt",
                 half_material_name="number_half_mt",
                 total_frames=60,
                 chances=None):
        self.logger = logger

        bpy.ops.wm.open_mainfile(filepath=blend_file_path)
        self.logger.info(f"Successfully loaded {blend_file_path}")

        self.on_mat = bpy.data.materials.get(on_material_name)
        self.off_mat = bpy.data.materials.get(off_material_name)
        self.half_mat = bpy.data.materials.get(half_material_name)

        self.total_frames = total_frames

        self.chances = Chances()
        for k, v in ({} if chances is None else chances).items():
            self.chances.k = v

        if not all([self.on_mat, self.off_mat, self.half_mat]):
            self.logger.warning(f"Available materials:")
            for mat in bpy.data.materials:
                self.logger.warning(f"  - {mat.name}")
            raise ValueError("Materials not found.")

        # Set up tubes mesh lookup, navigating through object structure
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
        if DEVICE_TYPE is not None:
            bpy.context.preferences.addons["cycles"].preferences.compute_device_type = DEVICE_TYPE

            bpy.context.preferences.addons["cycles"].preferences.get_devices()
            for device in bpy.context.preferences.addons["cycles"].preferences.devices:
                device.use = True  # Enable all available GPUs
            bpy.context.scene.cycles.device = "GPU"

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

    def render_frame(self, frame=1, output_dir="./blender/output", filename="nixie_render"):
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        bpy.context.scene.frame_set(frame)
        output_path = os.path.abspath(os.path.join(output_dir, filename))
        bpy.context.scene.render.filepath = output_path

        self.logger.info(f"Rendering frame to {output_path}")
        self.logger.debug(f"Res: {bpy.context.scene.render.resolution_x}x{bpy.context.scene.render.resolution_y}")

        bpy.ops.render.render(write_still=True)

        self.logger.info(f"Rendering complete: {output_path}")
        return output_path

    def animate_display(self, number: int, output_dir="./blender/output"):
        """Generates an animation with flickering tubes"""
        state = [self.on_mat] * DIGITS
        durations = [0] * DIGITS  # Number of frames tube is off

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
            self.render_frame(frame, output_dir, f"{number}/{frame}.png")

        self.logger.info("All frames rendered.")

        command = [
            "ffmpeg",
            "-framerate", "60",
            "-i", f"{number}/%d.png",
            "-vf", f"scale={EXPORT_GIF_WIDTH}:-1:flags=lanczos",
            "-r", "60",
            "-y", f"{number}.gif"
        ]

        subprocess.run(command, cwd=output_dir, check=True)
        self.logger.info(f"Exported as {number}.gif")


if __name__ == "__main__":
    try:
        renderer = Renderer(total_frames=TOTAL_FRAMES)
    except Exception as e:
        logger.error(f"Error loading blend file: {e}")
        exit(1)

    renderer.animate_display(0)
