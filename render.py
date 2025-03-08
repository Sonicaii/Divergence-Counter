"""Divergence View Renderer Server

@author: Sonicaii
@version: 0.1.0
"""

import bpy
import os
import logging
from pathlib import Path

__version__ = "0.1.0"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("render")

DIGITS = 8


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

        self.turn_off_dots()

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

    def _set_tube_digit(self, tube, digit: int):
        self.logger.debug(f"Setting tube {tube.name} to display digit {digit}")

        number_objs = [child for child in tube.children if child.name.startswith("number")]
        if not number_objs:
            self.logger.warning(f"No number objects found under {tube.name}")
            return

        number_obj = number_objs[0]

        filaments = [child for child in number_obj.children
                     if child.name.startswith("num") and not child.name.startswith("numDot")]

        for filament in filaments:
            try:
                current_digit = int(filament.name.strip("num").split(".")[0])
                mesh_children = [child for child in filament.children if child.type == "MESH"]

                if not mesh_children:
                    self.logger.debug(f"No mesh children found for {filament.name}")
                    continue

                mesh_obj = mesh_children[0]

                if len(mesh_obj.material_slots) > 0:
                    if current_digit == digit:
                        mesh_obj.material_slots[0].material = self.on_mat
                        self.logger.debug(f"Set {mesh_obj.name} (digit {current_digit}) to ON")
                    else:
                        mesh_obj.material_slots[0].material = self.off_mat
                        self.logger.debug(f"Set {mesh_obj.name} (digit {current_digit}) to OFF")
            except ValueError:
                self.logger.debug(f"Could not parse digit from {filament.name}")

    def turn_off_dots(self):
        self.logger.debug("Turning off all dot indicators")

        for obj in bpy.data.objects:
            if "numDot" in obj.name and obj.type == "EMPTY":
                dot_meshes = [child for child in obj.children if child.type == "MESH"]
                for mesh in dot_meshes:
                    if len(mesh.material_slots) > 0:
                        mesh.material_slots[0].material = self.off_mat
                        self.logger.debug(f"Set {mesh.name} (dot) to OFF")

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
