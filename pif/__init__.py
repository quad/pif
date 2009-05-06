__all__ = [
    'flickr',
    'local',
    'ui',
    'workers',
]

import hashlib

TAILHASH_SIZE = 512

FORMATS = {
    'gif': 'gif',
    'jpeg': 'jpg',
    'jpg': 'jpg',
    'png': 'png',
}


def make_shorthash(tail, original_format, size, width, height):
    """Calculate a shorthash."""

    # Normalize the data.
    tail = hashlib.sha512(tail).digest()
    original_format = FORMATS[original_format.lower()]
    size, height, width = map(int, (size, height, width))

    values = tail, original_format, size, height, width

    return ':'.join(map(str, values))
