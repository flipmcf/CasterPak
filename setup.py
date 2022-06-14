from distutils.core import setup

setup(name='CasterPak',
      version='0.6',
      author="Michael McFadden (flipmcf)",
      author_email="flipmcf@gmail.com",
      py_modules=['casterpak'],
      install_requires=['flask',
                        'tinydb',
                        'requests',
                        'gunicorn',
                        ]
      )
