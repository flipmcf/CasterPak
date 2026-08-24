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


import logging
level = logging.DEBUG
logger = logging.getLogger("config")

def get_config() -> ConfigParser:
    """retrieves a configparser instance of the current application config.
    Note that although the config.ini will define the config schema and shape
    all config variables can be overridden with env vars.
    
    get_config() will read in the config.ini, then parse the env vars to override any config values.
    env vars don't magically create new config entries for the most part, so start with config.ini
    """
    ## We might change this later to read in all env vars that begin CASTERPAK_ and create new sections... 
    ## I'm just not ready to do that yet.

    logger.debug("config was (re)read.")
    config: ConfigParser = configparser.ConfigParser()
    
    successfully_read = config.read('config.ini')

    if 'config.ini' not in successfully_read:
        raise FileNotFoundError("""
        config file config.ini not found.
        Copy config_example.ini to config.ini and configure the application
        """)



    for section in config.sections():
        prefix = f"CASTERPAK_{section.upper()}_"

        # 1. Gather all environment variables destined for this specific section
        env_vars_for_section = {
            k: v for k, v in os.environ.items() if k.startswith(prefix)
        }
        
        # 2.Special case for encoding_ladder: 
        #   If custom ladder env vars exist, annihilate the defaults and rewrite the section.
        if section == 'encoding_ladder' and env_vars_for_section:
            config.remove_section('encoding_ladder')
            config.add_section('encoding_ladder')

        # 3. Inject the environment variables into the config
        for env_key, env_val in env_vars_for_section.items():
            # Strip the prefix to get the raw option name and lowercase it
            option = env_key[len(prefix):].lower() 
            config.set(section, option, env_val)

    return config
