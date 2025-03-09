"""Divergence View Renderer Server

@author: Sonicaii
@version: 0.1.2
"""

import bpy
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

__version__ = "0.1.2"

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
DEVICE_TYPE = os.environ.get("RENDER_DEVICE_TYPE")


class Renderer:
    def __init__(self, blend_file_path="blender/tubes.blend",
                 on_material_name="number_on_mt",
                 off_material_name="number_off_mt"):
        self.logger = logger

        bpy.ops.wm.open_mainfile(filepath=blend_file_path)
        self.logger.info(f"Successfully loaded {blend_file_path}")

        self.on_mat = bpy.data.materials.get(on_material_name)
        self.off_mat = bpy.data.materials.get(off_material_name)

        if not self.on_mat or not self.off_mat:
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

    def set_display_number(self, number: int | str):
        """Iterates through all tubes' meshes and toggles filaments to match. Non digit character = Tube off"""
        if isinstance(number, int):
            number = str(number).zfill(DIGITS)
        if len(number) > DIGITS:
            raise ValueError(f"{number} has more than {DIGITS} digits!")
        self.logger.info(f"Setting display to: {number}")

        for tube, digit in enumerate(number):
            for i, filament in enumerate(self._tubes[tube]):
                if str(i) == digit:
                    filament.material_slots[0].material = self.on_mat
                    self.logger.debug(f"Set {filament.name} (digit {i}) to ON")
                else:
                    filament.material_slots[0].material = self.off_mat
                    self.logger.debug(f"Set {filament.name} (digit {i}) to OFF")

        bpy.context.view_layer.update()
        return True

    def render_frame(self, frame=1, output_dir="./blender/output", filename="nixie_render"):
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        bpy.context.scene.frame_set(frame)
        output_path = os.path.abspath(os.path.join(output_dir, filename))
        bpy.context.scene.render.filepath = output_path

        self.logger.info(f"Rendering frame to {output_path}")
        self.logger.info(f"Resolution: {bpy.context.scene.render.resolution_x}x{bpy.context.scene.render.resolution_y}")

        bpy.ops.render.render(write_still=True)

        self.logger.info(f"Rendering complete: {output_path}")
        return output_path


if __name__ == "__main__":
    try:
        renderer = Renderer()
    except Exception as e:
        logger.error(f"Error loading blend file: {e}")
        exit(1)

    renderer.set_display_number(0)
    output = renderer.render_frame()
