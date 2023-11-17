from setuptools import setup, find_packages

with open("requirements.txt") as f:
	install_requires = f.read().strip().split("\n")

# get version from __version__ variable in phamos/__init__.py
from phamos import __version__ as version

setup(
	name="phamos",
	version=version,
	description="ERPNext Enhancement for Phamos.eu",
	author="phamos.eu",
	author_email="support@phamos.eu",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires
)
