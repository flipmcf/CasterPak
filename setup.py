# Copyright (c) 2026, Michael McFadden & Radio Free Asia
# GNU GENERAL PUBLIC LICENSE Version 2
# See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
from distutils.core import setup

from setuptools import setup
from setuptools.command.egg_info import egg_info

class egg_info_ex(egg_info):
    """Includes license file into `.egg-info` folder."""

    def run(self):
        # don't duplicate license into `.egg-info` when building a distribution
        if not self.distribution.have_run.get('install', True):
            # `install` command is in progress, copy license
            self.mkpath(self.egg_info)
            self.copy_file('LICENSE', self.egg_info)

        egg_info.run(self)


# TODO: Pin dependencies to specific versions
setup(name='CasterPak',
      version='0.8',
      author="Michael McFadden (flipmcf)",
      author_email="flipmcf@gmail.com",
      py_modules=['casterpak'],
      license_files = ('LICENSE',),
      cmdclass = {'egg_info': egg_info_ex},
      install_requires=['flask',
                        '',
                        'requests',
                        'gunicorn',
                        ]
      )
