# Divergence Counter

Simple web view counter with nixie tubes

[//]: # (![Moe-Counter]&#40;http://projectgungame.top:13102/Divergence-Counter.github&#41;)

## Installation
### Web backend

```shell
$ mkdir counter
$ cd counter
$ python3 -m venv venv
$ source venv/bin/activate
$ python3 -m pip install aiohttp bpy imageio starlette python-dotenv uvicorn[standard]

$ uvicorn --host 0.0.0.0 --port 8800 app:app
```

### Renderer Server
Install [blender](https://www.blender.org/download/).
```shell
winget install BlenderFoundation.Blender
winget install Gyan.FFmpeg
```
Set up .env and adjust for your system.
```dotenv
RENDER_SAMPLES=1028
RENDER_DEVICE_TYPE="OPTIX"  # Or "CUDA" etc. Leave blank for CPU 
RENDER_TOTAL_FRAMES=30
RENDER_FPS=30
RENDER_QUALITY=95
```
```shell
$ uvicorn --host 0.0.0.0 --port 8801 render:app
```
*Remember to set IP to `127.0.0.1` if using a reverse proxy.*
## Credits

*   [Moe-Counter](https://github.com/journey-ad/Moe-Counter/)
*   [3D Model](https://www.artstation.com/amatsukast)
*   [Original Tube Renders](https://github.com/dogancelik/divergence-meter/)
