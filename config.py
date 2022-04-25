import configparser

from configparser import ConfigParser


def get_config() -> ConfigParser:
    config: ConfigParser = configparser.ConfigParser()
    successfully_read = config.read('config.ini')

    if 'config.ini' not in successfully_read:
        raise FileNotFoundError('config file config.ini not found')


    return config
