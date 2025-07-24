import logging
import json
from pathlib import Path

# pip install rich
import rich


class LazySettings:
    """A class to lazily load settings from a JSON file. Inspired from Django's settings."""

    def __init__(self, config_file="./config.json"):
        self._config_file = config_file
        self._config = {}
        self._loaded = False

    def _load_config(self):
        if not self._loaded:
            try:
                with open(self._config_file, "r") as f:
                    self._config = json.load(f)
                self._loaded = True
            except FileNotFoundError:
                rich.print(
                    f"[red]Configuration file {self._config_file} not found. Using default settings.[/red]"
                )
                self._config = {}
                self._loaded = True
            except json.JSONDecodeError as e:
                rich.print(
                    f"[red]Error decoding JSON from {self._config_file}: {e}[/red]"
                )
                self._config = {}
                self._loaded = True

    def __getattr__(self, name):
        self._load_config()

        default = {"PORT": 8000, "HOST": "localhost", "ROOT": "."}
        if name == "ROOT":
            value = self._config.get(name, default[name])
            return Path(value).resolve()
        elif name == "PORT":
            return int(self._config.get(name, default[name]))
        elif name == "HOST":
            return self._config.get(name, default[name])
        elif name == "LEVEL":
            return self._config.get(name, "INFO").upper()


    def __contains__(self, item):
        self._load_config()
        return item.lower() in self._config

    def get(self, key, default=None):
        try:
            return getattr(self, key.upper())
        except KeyError:
            return default

    def reload(self):
        self._loaded = False
        self._config = {}
        self._load_config()

    
    @property
    def logger(self):
        if not hasattr(self, "_logger") or self._logger is None:
            self._logger = self._setup_logger()
        return self._logger

    def _setup_logger(self) -> logging.Logger:
        """Sets up the logger with the appropriate level and handlers."""
        self._load_config()
        level = getattr(self, "LEVEL", "INFO")
        logging.basicConfig(level=level)
        logger = logging.getLogger("nginx_clone")
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        return logger

    def configure(self, **kwargs):
        self._load_config()
        self._config.update(kwargs)


settings = LazySettings()