import os
from setuptools import setup

def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

version = '0.1.0'

setup(
    name='beancountASN',
    version=version,
    author='bramhooimeijer',
    author_email='33625980+bramhooimeijer@users.noreply.github.com',
    description='Converts ASN .csv to Beancount',
    long_description=read('README.md'),
    url='https://github.com/bramhooimeijer/beancount-asn',
    license='GPLv2',
    packages=['beancountASN']
    )
