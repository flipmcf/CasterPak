import os
import logging
from logging.config import dictConfig

from flask import Flask

import applogging
from config import get_config


def setup_gunicorn_logging(app, base_config):
    # get the gunicorn logger
    gunicorn_logger = logging.getLogger('gunicorn.error')

    # configure the app, and vodhls loggers to use the same handlers as gunicorn
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
    
    vodhls_logger = logging.getLogger('vodhls')
    vodhls_logger.handlers = gunicorn_logger.handlers
    vodhls_logger.setLevel(gunicorn_logger.level)
    
    cleanup_logger = logging.getLogger('CasterPak-cleanup')
    cleanup_logger.handlers = gunicorn_logger.handlers
    cleanup_logger.setLevel(gunicorn_logger.level)



def create_app(test_config=None):
    # create and configure the app
    app = Flask(__name__, instance_relative_config=True)

    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    if test_config is None:
        # load the instance config, if it exists, when not testing
        base_config = get_config()
    else:
        # load the test config if passed in
        base_config = test_config

    logging_config = applogging.CASTERPAK_DEFAULT_LOGGING_CONFIG
    dictConfig(logging_config)

    if base_config.getboolean('application', 'debug'):
        app.config['DEBUG'] = True

    app.config.update(base_config)

    if app.config['output'].get('serverName'):
        app.logger.info(f"casterpak server name is {app.config['output'].get('serverName')} ")
        app.logger.info("flask app server name not set")

    # initialize segment directory
    if not os.path.isdir(app.config['output']['segmentParentPath']):
        os.mkdir(app.config['output']['segmentParentPath'])
        app.logger.debug(f"created new output directory {app.config['output']['segmentParentPath']}")
    app.logger.info(f"output directory set to {app.config['output']['segmentParentPath']}")

    # initialize input cache directory
    if app.config['input']['input_type'] == 'filesystem' and \
            app.config['filesystem'].getboolean('cache_input') is False:
        app.logger.debug("input caching disabled")
    else:
        if not os.path.isdir(app.config['input']['videoCachePath']):
            os.mkdir(app.config['input']['videoCachePath'])
            app.logger.debug(f"created new input cache directory {app.config['input']['videoCachePath']}")
        app.logger.info("input caching enabled")
        app.logger.info(f"input caching to {app.config['input']['videoCachePath']}")

    if __name__ != "__main__":
        setup_gunicorn_logging(app, base_config)

    from . import routes
    app.register_blueprint(routes.bp)

    return app
