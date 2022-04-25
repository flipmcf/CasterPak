import datetime


def addrecord(filename=None,timestamp=None):
    if timestamp is None:
        timestamp = datetime.datetime.now(datetime.timezone.utc)
    return False
