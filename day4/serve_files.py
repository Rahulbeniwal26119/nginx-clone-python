import email.utils
import hashlib
from settings import settings

logger = settings.logger


def make_etag(file_stats):
    last_modified = file_stats.st_mtime
    size = file_stats.st_size
    etag = hashlib.md5(f"{last_modified}-{size}".encode("utf-8")).hexdigest()
    lm = email.utils.formatdate(last_modified, usegmt=True)
    return etag, lm


def parse_last_modified_since(lms):
    try:
        lms_time = email.utils.mktime_tz(email.utils.parsedate_tz(lms))
    except Exception as e:
        logger.exception("Failed to parse Last-Modified-Since header", e)
        lms_time = None
    return lms_time
