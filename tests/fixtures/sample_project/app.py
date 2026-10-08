import os
from pathlib import Path as FilePath


class Greeter:
    def greet(self, name):
        return f"Hello, {name}!"


async def fetch_message():
    return os.path.join("hello", "world")