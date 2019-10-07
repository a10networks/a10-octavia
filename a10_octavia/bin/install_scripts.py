import setuptools
import os
from setuptools import setup
from setuptools.command.develop import develop


def main(self):
    print("aeeee halllooo")
    current_dir_path = os.path.dirname(os.path.realpath(__file__))
    create_service_script_path = os.path.join(current_dir_path, 'bin',
                                              'create_service.sh')
    subprocess.check_output([create_service_script_path])


