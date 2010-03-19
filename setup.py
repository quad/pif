#!/usr/bin/env python

from setuptools import setup

setup(
    name='pif',
    version='9.4',

    packages=[
        'pif',
        'pif.ui',
    ],
    package_data={
        'pif': ['flickr-api.key'],
        'pif.ui': ['preview.glade'],
    },

    install_requires=[
        'eventlet',
        'flickrapi',
    ],

    entry_points={
        'console_scripts': [
            'pif = pif.ui.console:run',
        ],
        'gui_scripts': [
            'pif-gtk = pif.ui.x:run',
        ],
    },

    tests_require=[
        'MiniMock',
        'nose',
    ],

    test_suite='nose.collector',
)
