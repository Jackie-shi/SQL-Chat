import logging  # Setting up the loggings to monitor gensim

global logger

logger = logging.getLogger('my_logger_public')
logger.setLevel(logging.INFO)
file_handler = logging.FileHandler('run_public.log')
formatter = logging.Formatter('%(levelname)s - %(asctime)s: %(message)s')
file_handler.setFormatter (formatter)
logger.addHandler(file_handler)