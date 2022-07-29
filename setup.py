from distutils.core import setup

setup(name='CasterPak',
      version='0.7',
      author="Michael McFadden (flipmcf)",
      author_email="flipmcf@gmail.com",
      py_modules=['casterpak'],
      install_requires=['flask',
                        '',
                        'requests',
                        'gunicorn',
                        ]
      )
