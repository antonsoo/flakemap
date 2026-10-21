import os


def test_pass():
    pass


def test_crash():
    os._exit(13)
