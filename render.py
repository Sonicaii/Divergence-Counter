"""Divergence View Renderer Server

@author: Sonicaii
@version: 2.0.0
"""
import asyncio
import logging
import os
import random
import shutil
import subprocess
import tempfile
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import bpy
from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.responses import Response, JSONResponse
from starlette.routing import Route

__version__ = "2.0.0"


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

SAMPLES = int(os.getenv("RENDER_SAMPLES", 4096))
DEVICE_TYPE = os.getenv("RENDER_DEVICE_TYPE", "OPTIX")
TOTAL_FRAMES = int(os.getenv("RENDER_TOTAL_FRAMES", 60))
BLEND_FILE_PATH = os.getenv("BLEND_FILE_PATH", "./blender/tubes.blend")
RENDER_OUTPUT_DIR = os.getenv("RENDER_OUTPUT_DIR", "./blender/output")
CACHE_DIR = os.getenv("CACHE_DIR", "./cache")
LOOKAHEAD = int(os.getenv("LOOKAHEAD", 5))

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
    logger.debug(f"Enabled GPU devices: {', '.join(active_devices)}")

bpy.context.scene.cycles.samples = SAMPLES
logger.info(
    f"Set render engine to {bpy.context.scene.render.engine} and device type to " +
    bpy.context.preferences.addons["cycles"].preferences.compute_device_type
)


class Queue:
    def __init__(self):
        self.data = OrderedDict()

    def __call__(self, item):  # Append
        if item not in self.data:
            self.data[item] = None

    def pop(self):
        return self.data.popitem(last=False)[0] if self.data else None


def get_tubes():
    tubes = []
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

        tubes.append(meshes)
    return tubes


def render_frame(output: Path, frame=1):
    output.parent.mkdir(parents=True, exist_ok=True)

    bpy.context.scene.frame_set(frame)
    bpy.context.scene.render.filepath = str(output)

    logger.info(f"Rendering frame to {output}")
    logger.debug(f"Res: {bpy.context.scene.render.resolution_x}x{bpy.context.scene.render.resolution_y}")

    bpy.ops.render.render(write_still=True)

    logger.info(f"Rendering complete: {output}")
    return output


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
        bpy.ops.wm.open_mainfile(filepath=blend_file_path)
        logger.info(f"Successfully loaded {blend_file_path}")

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
            logger.warning(f"Available materials:")
            for mat in bpy.data.materials:
                logger.warning(f"  - {mat.name}")
            raise ValueError("Materials not found.")

        # Set up tubes mesh lookup, navigating through object structure
        # _tubes is a 2D list of tubes (lists of length DIGITS) that holds 10 filaments (bpy.types.Object)
        self.tubes = get_tubes()

        self.queue = Queue()
        self.rerender = Queue()
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self._start_loop, daemon=True).start()

    def _start_loop(self):
        """Runs the asyncio event loop in a background thread."""
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.process_queue())

    def __call__(self, *numbers):
        """Adds numbers to the render queue if not already enqueued and not already rendered before."""
        for number in numbers:
            cache_path = Path(CACHE_DIR) / f"{number}.webp"
            render_path = Path(RENDER_OUTPUT_DIR) / f"{number}.webp"

            if not (cache_path.exists() or render_path.exists()):
                self.queue(number)
            else:
                logger.debug(f"Skipping {number}")

    async def process_queue(self):
        """Processes the render queue sequentially, ensuring no concurrency."""
        while True:
            try:
                number = self.queue.pop()
                if number is None:
                    number = self.rerender.pop()
                if number is not None:
                    await asyncio.to_thread(self.animate_display, number, RENDER_OUTPUT_DIR)
            except Exception as ex:
                logger.error(ex)

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

        # state_str = "".join([{self.on_mat: "█", self.half_mat: "░", self.off_mat: "_"}[s] for s in state])
        logger.info(f"Setting tubes:  {number}")
        # logger.info(f"Setting states: {state_str}")

        for tube, digit in enumerate(number):
            for i, filament in enumerate(self.tubes[tube]):
                if str(i) == digit:
                    filament.material_slots[0].material = state[tube]
                else:
                    filament.material_slots[0].material = self.off_mat
                logger.debug(f"Set {filament.name} (digit {i}) to {filament.material_slots[0].material}")

        bpy.context.view_layer.update()
        return True

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
                render_frame(tmp_folder / f"{frame}.png", frame)

            logger.info("All frames rendered.")

            command = [
                "ffmpeg",
                "-framerate", "60",
                "-i", str(tmp_folder / "%d.png"),
                "-c:v", "libwebp",
                "-lossless", "1",
                "-loop", "0",  # Loop forever
                "-preset", "default",
                "-r", "60",
                "-y", f"{number}.webp"
            ]

            subprocess.run(command, cwd=output_dir, check=True)
            logger.info(
                "Exported as %s.webp in %.2f seconds",
                Path(output_dir) / str(number),
                round(time.perf_counter() - start, 2)
            )


async def serve(request):
    number = int(request.path_params["number"])
    """Serves file if cached, or triggers rendering if not."""
    Path(RENDER_OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)

    filename = f"{number}.webp"
    source_path = Path(RENDER_OUTPUT_DIR) / filename
    cache_path = Path(CACHE_DIR) / filename
    future_paths = (Path(RENDER_OUTPUT_DIR) / f"{number+LOOKAHEAD}.webp").exists() or \
                   (Path(CACHE_DIR) / f"{number+LOOKAHEAD}.webp").exists()

    # Update cache with new version
    if source_path.exists():
        shutil.move(source_path, cache_path)

    # First time encountering number, queue up extra numbers ahead
    if not cache_path.exists() or not future_paths:
        request.app.render(*range(number, number + LOOKAHEAD + 1))
        logger.debug(f"Queued {number} to {number + LOOKAHEAD}")
    else:
        request.app.render.rerender(number)
        logger.debug(f"Queued {number} for re-rendering")

    if not cache_path.exists():
        raise HTTPException(status_code=404)

    return Response(cache_path.read_bytes(), media_type="image/webp")


async def get_queue(request):
    return JSONResponse([*request.app.render.queue.data, *request.app.render.rerender.data])


try:
    app = Starlette(routes=[Route("/{number:int}", serve), Route("/", get_queue)])
    app.render = Renderer(total_frames=TOTAL_FRAMES)
except Exception as e:
    logger.error(f"Error setting up renderer: {e}")
    exit(1)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8801)
