#Copyright (c) 2022, Michael McFadden & Radio Free Asia
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
import os
import configparser

from configparser import ConfigParser

# set current working directory
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

    for section in config.sections():
        for option in config.options(section):
            env_var = f"CASTERPAK_{section.upper()}_{option.upper()}"
            if env_var in os.environ:
                print(f"Overriding config option {section}.{option} with environment variable {env_var}")
                config.set(section, option, os.environ[env_var])

    return config
