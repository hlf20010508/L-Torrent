__author__ = 'L-ING'

import codecs
import re

from setuptools import setup

with codecs.open("__init__.py") as file:
    version = re.search(
        r'^__version__\s*=\s*[\'"]([^\'"]*)[\'"]',
        file.read(),
        re.MULTILINE,
    ).group(1)

with codecs.open("../README.md", encoding="utf-8") as file:
    readme = file.read()

setup(
    name="ltorrent-async",
    description="A pure python torrent client based on PyTorrent",
    author="L-ING",
    url="https://github.com/hlf20010508/LTorrent",
    author_email="hlf01@icloud.com",
    version=version,
    long_description_content_type="text/markdown",
    package_dir={"ltorrent_async": "../ltorrent_async"},
    packages=["ltorrent_async"],
    install_requires=[
        "bcoding",
        "bitstring",
        "ipaddress",
        "aiohttp",
    ],
    license="Unlicense license",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: The Unlicense (Unlicense)",
        "Natural Language :: English",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    long_description=readme,
    package_data={"": ["../LICENSE", "../README.md"]},
    include_package_data=True,
    python_requires=">=3.8",
)