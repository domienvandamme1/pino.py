import json
import sys
import os
import socket
from datetime import datetime
from collections import namedtuple
from .utils import merge_dicts
from os import getpid


LoggingLevel = namedtuple('LoggingLevel', ['name', 'level'])
PinoConfig = namedtuple('PinoConfig', [
    'level', 'stream', 'enabled', 'bindings', 'messagekey', 'millidiff', 'parent'
])

DEBUG = LoggingLevel("debug", 20)
INFO = LoggingLevel("info", 30)
WARN = LoggingLevel("warn", 40)
ERROR = LoggingLevel("error", 50)
CRITICAL = LoggingLevel("critical", 60)

LEVELS = [DEBUG, INFO, WARN, ERROR, CRITICAL]
LEVEL_NAMES = [level.name for level in LEVELS]
LEVEL_BY_NAME = {level.name: level for level in LEVELS}
LEVEL_BY_CODE = {level.level: level for level in LEVELS}

def get_level(level_name_or_code):
    if isinstance(level_name_or_code, LoggingLevel):
        return level_name_or_code
    if isinstance(level_name_or_code, int):
        return LEVEL_BY_CODE.get(level_name_or_code)
    return LEVEL_BY_NAME.get(level_name_or_code)


hostname = socket.gethostname()


def get_logger(self, level):
    metas = self._config.bindings or {}
    stream = self._config.stream
    message_key = self._config.messagekey
    should_millidiff = self._config.millidiff

    def log(*args, **kwargs):
        has_meta = isinstance(args[0], dict)

        if has_meta:
            message_metas = args[0]
            complete_metas = merge_dicts(message_metas, metas)
            args = args[1:] # shift args
        else:
            complete_metas = metas

        if len(args) > 1:
            message = args[0] % args[1:]
        elif len(kwargs):
            message = args[0].format(**kwargs)
        else:
            message = args[0]

        now = int(1000* datetime.now().timestamp())
        json_log = {
            "level": level.level,
            "time": now,
            'pid': getpid(),
            message_key: message,
            "hostname": hostname,
            **complete_metas
        }
        if should_millidiff:
            delta = (now - self._last_timestamp) if self._last_timestamp else 0
            json_log["millidiff"] = delta
            self._last_timestamp = now
        stream.write(self._dumps(json_log))
        stream.write(os.linesep)
        stream.flush()
    log.__name__ = level.name
    return log

class DummyLogger:
    def critical(self, *args, **kwargs):
        pass
    def error(self, *args, **kwargs):
        pass
    def warn(self, *args, **kwargs):
        pass
    def info(self, *args, **kwargs):
        pass
    def debug(self, *args, **kwargs):
        pass

class PinoLogger(DummyLogger):
    __slots__ = ["_config", "_last_timestamp", "_dumps"]

    def __init__(
        self,
        bindings=None, level="info", stream=sys.stdout,
        enabled=True, parent=None, millidiff=True, messagekey="msg",
        dump_function=json.dumps
    ):
        logging_level = get_level(level)
        self._config = PinoConfig(logging_level, stream, enabled, bindings, messagekey, millidiff, parent)
        self._last_timestamp = None
        self._setup_logging(self._config)
        self._dumps = dump_function

    def _setup_logging(self, config):
        if config.enabled:
            for level in LEVELS:
                logging_method = get_logger(self, level) if level.level >= config.level.level \
                    else getattr(super(), level.name)
                setattr(self, level.name, logging_method)

    @property
    def level(self):
        return self._config.level.name

    @level.setter
    def level(self, new_level):
        self._config = self._config._replace(level=get_level(new_level))
        self._setup_logging(self._config)

    def child(self, metas=None, **kwargs_metas):
        merged_bindings = merge_dicts(metas or kwargs_metas, self._config.bindings)
        child_logger = PinoLogger(
            **self._config._replace(parent=self, bindings=merged_bindings)._asdict(),
            dump_function=self._dumps
        )
        child_logger._last_timestamp = self._last_timestamp
        return child_logger
