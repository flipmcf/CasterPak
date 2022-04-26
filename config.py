import os
import configparser

from configparser import ConfigParser

#set current working directory
abspath = os.path.abspath(__file__)
dname = os.path.dirname(abspath)
os.chdir(dname)

def get_config() -> ConfigParser:
    config: ConfigParser = configparser.ConfigParser()
    successfully_read = config.read('config.ini')

    if 'config.ini' not in successfully_read:
        raise FileNotFoundError("""
        config file config.ini not found.
        Copy config_example.ini to config.ini and configure the application
        """)

    return config
