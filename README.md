# Divergence Counter

Simple web view counter with nixie tubes

![Moe-Counter](http://projectgungame.top:13102/Divergence-Counter.github)


## Usage

### Install

#### Deploying on your own server

```shell
$ mkdir counter
$ cd counter
$ python3 -m venv venv
$ source venv/bin/activate
$ pip install flask gunicorn

$ gunicorn --bind 0.0.0.0:8000 app:app
```

## Credits

*   [Moe-Counter](https://github.com/journey-ad/Moe-Counter/)
