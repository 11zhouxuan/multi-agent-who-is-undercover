import os  
import logging 
import threading 
logger_lock = threading.Lock()


class Logger:
    logger_map = {}
    @classmethod
    def _get_logger(
        cls,
        name,
        level=int(os.environ.get('DEBUG_LEVEL',logging.INFO)),
        format='%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s',
        datefmt='%Y-%m-%d:%H:%M:%S'
        ):
        if name in cls.logger_map:
            return cls.logger_map[name]
        logger = logging.getLogger(name)
        logger.propagate = 0
        # Create a handler
        c_handler = logging.StreamHandler()
        formatter = logging.Formatter(format, datefmt=datefmt)
        c_handler.setFormatter(formatter)
        logger.addHandler(c_handler)
        logger.setLevel(level) 

        cls.logger_map[name] = logger
        return logger
    
    @classmethod
    def get_logger(
        cls,
        *args,
        **kwargs
        ):
        with logger_lock:
            return cls._get_logger(*args,**kwargs)
    
get_logger = Logger.get_logger