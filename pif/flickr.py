import logging
import time

import flickrapi
import pkg_resources

API_KEY, API_SECRET = pkg_resources.resource_string(__name__, 'flickr-api.key').split()

def _default_proxy_cb():
    logging.info('Waiting for authorization from Flickr...')
    time.sleep(5)

def get_proxy(key = API_KEY, secret = API_SECRET, wait_callback = _default_proxy_cb):
    # Setup the API proxy.
    proxy = flickrapi.FlickrAPI(key, secret, format = 'etree')

    # Authorize.
    auth_response = proxy.get_token_part_one(perms = 'write')

    while True:
        try:
            if proxy.get_token_part_two(auth_response):
                break
        except flickrapi.exceptions.FlickrError, e:
            # Wait for frob confirmation.
            if 'Error: 108' in e.message and not wait_callback():
                continue
            raise

    return proxy


