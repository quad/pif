#!/usr/bin/env python

from setuptools import setup

setup(
    name = 'pif',
    version = '9.1',

    packages = ['pif',],
    package_data = {
        'pif': ['flickr-api.key'],
    },

    install_requires = [
        'flickrapi',
        'httplib2',
        'threadpool',
    ],

    entry_points = {
        'console_scripts': [
            'pif = pif.cmd:run',
            'pif-add = pif.cmd:add',
            'pif-status = pif.cmd:status',
            'pif-refresh = pif.cmd:refresh',
            'pif-rebuild = pif.cmd:rebuild',
        ]
    },

    test_suite = 'nose.collector',
)
