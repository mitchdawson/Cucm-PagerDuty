import logging
import time

from logging.handlers import TimedRotatingFileHandler
from logging.handlers import RotatingFileHandler


# ----------------------------------------------------------------------
# def create_timed_rotating_log(path):
#     """"""
#     logger = logging.getLogger("Rotating Log")
#     logger.setLevel(logging.INFO)
#
#     handler = TimedRotatingFileHandler(path,
#                                        when="m",
#                                        interval=1,
#                                        backupCount=5)
#     logger.addHandler(handler)
#
#     for i in range(6):
#         logger.info("This is a test!")
#         time.sleep(75)


# ----------------------------------------------------------------------
# if __name__ == "__main__":
#     log_file = "timed_test.log"
#     create_timed_rotating_log(log_file)


def create_rotating_log(path):

    logger = logging.getLogger('Rotating log')
    logger.setLevel(logging.DEBUG)

    # f = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s').format(ascti)
    f = logging.Formatter(
        '%(asctime)s - %(funcName)s - %(levelname)s - %(message)s')
    handler = RotatingFileHandler(
        path, mode='a', maxBytes=1000, backupCount=10)
    handler.setFormatter(f)
    logger.addHandler(handler)

    for i in range(100):
        logger.info('THIS IS AN INFO MESSAGE PLEASE LOG IT')


if __name__ == '__main__':
    logfile = 'rotetest.txt'
    create_rotating_log(logfile)
