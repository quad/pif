#!/usr/bin/env python

from setuptools import setup

setup(
    name='pif',
    version='10.3',

    packages=['pif',],
    package_data={
        'pif': ['flickr-api.key'],
    },

    install_requires=[
        'flickrapi',
        'httplib2',
        'simplejson',
        'threadpool',
    ],

    entry_points={
        'console_scripts': [
            'pif = pif.ui.console:run',
            'xpif = pif.ui.x:run',
        ]
    },

    tests_require=[
        'MiniMock',
        'nose',
    ],

    test_suite='nose.collector',
)
