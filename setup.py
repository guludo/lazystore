import pathlib

import setuptools


setuptools.setup(
    name='lazystore',
    version='0.1.0',
    url='https://github.com/guludo/lazystore',
    description='Store of values created on demand.',
    long_description=(pathlib.Path(__file__).parent / 'README.rst').read_text(),
    long_description_content_type='text/x-rst',
    packages=['lazystore'],
    package_data={
        'lazystore': ['py.typed'],
    },
    extras_require={
        'dev': [
            'coverage~=6.2',
            'mypy>=0.931<1',
            'pytest~=6.2',
            'pytest-doctestplus~=0.11.0',
        ]
    },
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)',
        'Programming Language :: Python :: 3',
    ],
    keywords=['lazy'],
)
