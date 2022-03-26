class ESHETException(Exception):
    pass


class Disconnected(ESHETException):
    """the server is or disconnected"""


class ErrorValue(ESHETException):
    """an error was returned by the server"""
