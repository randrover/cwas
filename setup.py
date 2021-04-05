#!/usr/bin/env python3
"""Category-wide association study (CWAS)
"""
import setuptools

setuptools.setup(
    name="cwas",
    version="1.0.0",
    author_email="mwjeong.sci@gmail.com",
    description=__doc__,
    url="https://github.com/mwjjeong/cwas",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: Linux",
    ],
    python_requires='>=3.7',
    include_package_data=True,
    entry_points={
        'console_scripts': [
            'cwas = cwas.__main__:main'
        ]
    }
)

