"""Logging configuration for LogAnomaly."""

import logging.config

LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        },
    },
    'handlers': {
        'default': {
            'level': 'INFO',
            'formatter': 'standard',
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stdout',
        },
        'file': {
            'level': 'DEBUG',
            'formatter': 'standard',
            'class': 'logging.FileHandler',
            'filename': 'loganomaly.log',
            'mode': 'a',
        }
    },
    'loggers': {
        '': {  # root logger
            'handlers': ['default'],
            'level': 'INFO',
            'propagate': True
        },
        'loganomaly': {
            'handlers': ['default', 'file'],
            'level': 'INFO',
            'propagate': False
        },
        'drain3': {  # Make Drain3 quieter
            'handlers': ['file'],
            'level': 'ERROR',
            'propagate': False
        },
    }
}

def setup_logging():
    """Set up logging configuration."""
    logging.config.dictConfig(LOGGING_CONFIG)
