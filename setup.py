from distutils.core import setup

setup(name='CasterPak',
      version='0.4',
      author="Michael McFadden (flipmcf)",
      author_email="flipmcf@gmail.com",
      py_modules=['casterpak'],
      install_requires=['flask',
                        'tinydb',
                        'gunicorn',
                        ]
      )
