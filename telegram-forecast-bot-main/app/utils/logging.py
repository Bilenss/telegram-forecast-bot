import sys
from loguru import logger

def setup(level: str = "INFO"):
    logger.remove()
    logger.add(sys.stdout, level=level, backtrace=False, diagnose=False,
               format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>")
    return logger
