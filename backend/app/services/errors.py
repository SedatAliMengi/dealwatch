"""Errors raised by services. main.py turns them into HTTP responses."""


class NotFoundError(Exception):
    """-> 404"""


class ConflictError(Exception):
    """-> 409"""
