from pip.download import PipSession
from pip.req import parse_requirements
from setuptools import setup, find_packages

install_reqs = parse_requirements("./requirements.txt", session=PipSession())
install_requires = [str(ir.req).split('==')[0] for ir in install_reqs]
setup(
    name='gps-server',
    packages=find_packages(exclude=['examples', 'tests']),
    version='1.0',
    description='GPS Server and Kafka Producer',
    author='Abhishek Verma, Chirag',
    author_email='abhishek@quikmile.com',
    package_data={'': ['*.json']},
    install_requires=install_requires
)
