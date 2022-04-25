import configparser

from configparser import ConfigParser


def get_config() -> ConfigParser:
    config: ConfigParser = configparser.ConfigParser()
    config.read('config.ini')
    return config
