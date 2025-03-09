# Divergence Counter

Simple web view counter with nixie tubes

[//]: # (![Moe-Counter]&#40;http://projectgungame.top:13102/Divergence-Counter.github&#41;)


## Usage
### Install
#### Deploying on your own server
```shell
$ mkdir counter
$ cd counter
$ python3 -m venv venv
$ source venv/bin/activate
$ pip install bpy flask gunicorn python-dotenv

$ gunicorn --bind 0.0.0.0:8000 app:app
```

Install blender

Example .env
```dotenv
RENDER_SAMPLES=4096
RENDER_DEVICE_TYPE="OPTIX"  # Or "CUDA" etc. Leave blank for CPU 
```

## Credits

*   [Moe-Counter](https://github.com/journey-ad/Moe-Counter/)
*   [3D Model](https://www.artstation.com/amatsukast)
