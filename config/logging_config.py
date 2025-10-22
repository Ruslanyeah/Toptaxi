import logging
import sys
from loguru import logger

def setup_logging():
    """
    Настраивает loguru для записи в консоль и в файлы с ротацией.
    """
    class InterceptHandler(logging.Handler):
        def emit(self, record):
            logger_opt = logger.opt(depth=6, exception=record.exc_info)
            logger_opt.log(record.levelname, record.getMessage())

    # This is the final, radical solution using logger.configure()
    # It atomically sets up the entire logging system.
    
    def patcher(record):
        # This patcher will now be applied to ALL records,
        # including those from the standard logging module.
        record["extra"].setdefault("user_id", "System")

    log_format = "{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{function}:{line} | user_id={extra[user_id]} | {message}"

    logger.configure(
        handlers=[
            {
                "sink": sys.stderr,
                "level": "INFO",
                "format": log_format,
            },
            {
                "sink": "logs/bot.log",
                "level": "INFO",
                "rotation": "10 MB",
                "compression": "zip",
                "enqueue": True,
                "backtrace": True,
                "diagnose": True,
                "format": log_format,
            },
        ],
        patcher=patcher,
        extra={} # Ensures the 'extra' dict is always available
    )

    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # Устанавливаем более высокий уровень для "шумных" логгеров
    logging.getLogger('apscheduler').setLevel(logging.WARNING)
    logging.getLogger('aiosqlite').setLevel(logging.WARNING)

    return logger