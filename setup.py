#!/usr/bin/env python
#
# Copyright 2014 Quantopian, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import print_function
import os
import re
import sys
from operator import lt, gt, eq, le, ge
from os.path import (
    abspath,
    dirname,
    join,
)
from packaging import version as packaging_version
from setuptools import (
    Extension,
    find_packages,
    setup,
)

import versioneer


class LazyBuildExtCommandClass(dict):
    """
    Lazy command class that defers operations requiring Cython and numpy until
    they've actually been downloaded and installed by setup_requires.
    """
    def __contains__(self, key):
        return (
            key == 'build_ext'
            or super(LazyBuildExtCommandClass, self).__contains__(key)
        )

    def __setitem__(self, key, value):
        if key == 'build_ext':
            raise AssertionError("build_ext overridden!")
        super(LazyBuildExtCommandClass, self).__setitem__(key, value)

    def __getitem__(self, key):
        if key != 'build_ext':
            return super(LazyBuildExtCommandClass, self).__getitem__(key)

        from Cython.Distutils import build_ext as cython_build_ext
        import numpy

        # Cython_build_ext isn't a new-style class in Py2.
        class build_ext(cython_build_ext, object):
            """
            Custom build_ext command that lazily adds numpy's include_dir to
            extensions.
            """
            def build_extensions(self):
                """
                Lazily append numpy's include directory to Extension includes.

                This is done here rather than at module scope because setup.py
                may be run before numpy has been installed, in which case
                importing numpy and calling `numpy.get_include()` will fail.
                """
                numpy_incl = numpy.get_include()
                for ext in self.extensions:
                    ext.include_dirs.append(numpy_incl)

                super(build_ext, self).build_extensions()
        return build_ext


def window_specialization(typename):
    """Make an extension for an AdjustedArrayWindow specialization."""
    return Extension(
        'zipline.lib._{name}window'.format(name=typename),
        ['zipline/lib/_{name}window.pyx'.format(name=typename)],
        depends=['zipline/lib/_windowtemplate.pxi'],
    )


ext_modules = [
    Extension('zipline.assets._assets', ['zipline/assets/_assets.pyx']),
    Extension('zipline.assets.continuous_futures',
              ['zipline/assets/continuous_futures.pyx']),
    Extension('zipline.lib.adjustment', ['zipline/lib/adjustment.pyx']),
    Extension('zipline.lib._factorize', ['zipline/lib/_factorize.pyx']),
    window_specialization('float64'),
    window_specialization('int64'),
    window_specialization('int64'),
    window_specialization('uint8'),
    window_specialization('label'),
    Extension('zipline.lib.rank', ['zipline/lib/rank.pyx']),
    Extension('zipline.data._equities', ['zipline/data/_equities.pyx']),
    Extension('zipline.data._adjustments', ['zipline/data/_adjustments.pyx']),
    Extension('zipline._protocol', ['zipline/_protocol.pyx']),
    Extension(
        'zipline.finance._finance_ext',
        ['zipline/finance/_finance_ext.pyx'],
    ),
    Extension('zipline.gens.sim_engine', ['zipline/gens/sim_engine.pyx']),
    Extension(
        'zipline.data._minute_bar_internal',
        ['zipline/data/_minute_bar_internal.pyx']
    ),
    Extension(
        'zipline.data._resample',
        ['zipline/data/_resample.pyx']
    ),
    Extension(
        'zipline.pipeline.loaders.blaze._core',
        ['zipline/pipeline/loaders/blaze/_core.pyx'],
        depends=['zipline/lib/adjustment.pxd'],
    ),
]


STR_TO_CMP = {
    '<': lt,
    '<=': le,
    '=': eq,
    '==': eq,
    '>': gt,
    '>=': ge,
}

SYS_VERSION = '.'.join(list(map(str, sys.version_info[:3])))


def _filter_requirements(lines_iter, filter_names=None,
                         filter_sys_version=False):
    for line in lines_iter:
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        match = REQ_PATTERN.match(line)
        if match is None:
            raise AssertionError("Could not parse requirement: %r" % line)

        name = match.group('name')
        if filter_names is not None and name not in filter_names:
            continue

        if filter_sys_version and match.group('pyspec'):
            pycomp, pyspec = match.group('pycomp', 'pyspec')
            comp = STR_TO_CMP[pycomp]
            pyver_spec = packaging_version.parse(pyspec)
            if comp(packaging_version.parse(SYS_VERSION), pyver_spec):
                # pip install -r understands lines with ;python_version<'3.0',
                # but pip install -e does not.  Filter here, removing the
                # env marker.
                yield line.split(';')[0]
            continue

        yield line


REQ_PATTERN = re.compile(
    r"(?P<name>[^=<>;]+)((?P<comp>[<=>]{1,2})(?P<spec>[^;]+))?"
    r"(?:(;\W*python_version\W*(?P<pycomp>[<=>]{1,2})\W*"
    r"(?P<pyspec>[0-9.]+)))?\W*"
)


def _conda_format(req):
    def _sub(m):
        name = m.group('name').lower()
        if name == 'numpy':
            return 'numpy x.x'
        if name == 'tables':
            name = 'pytables'

        comp, spec = m.group('comp', 'spec')
        if comp and spec:
            formatted = '%s %s%s' % (name, comp, spec)
        else:
            formatted = name
        pycomp, pyspec = m.group('pycomp', 'pyspec')
        if pyspec:
            # Compare the two-digit string versions as ints.
            selector = ' # [int(py) %s int(%s)]' % (
                pycomp, ''.join(pyspec.split('.')[:2]).ljust(2, '0')
            )
            return formatted + selector

        return formatted

    return REQ_PATTERN.sub(_sub, req, 1)


def read_requirements(path,
                      conda_format=False,
                      filter_names=None):
    """
    Read a requirements file, expressed as a path relative to Zipline root.
    """
    real_path = join(dirname(abspath(__file__)), path)
    with open(real_path, mode="r", encoding="utf-8") as f:
        reqs = _filter_requirements(f.readlines(), filter_names=filter_names,
                                    filter_sys_version=not conda_format)

        if conda_format:
            reqs = map(_conda_format, reqs)

        return list(reqs)


def install_requires(conda_format=False):
    return read_requirements('etc/requirements.in', conda_format=conda_format)


def extras_requires(conda_format=False):
    extras = {
        extra: read_requirements('etc/requirements_{0}.in'.format(extra),
                                 conda_format=conda_format)
        for extra in ('dev', 'talib')
    }
    extras['all'] = [req for reqs in extras.values() for req in reqs]
    print(extras)

    return extras


def setup_requirements(requirements_path, module_names,
                       conda_format=False):
    module_names = set(module_names)
    module_lines = read_requirements(requirements_path,
                                     conda_format=conda_format,
                                     filter_names=module_names)

    if len(set(module_lines)) != len(module_names):
        raise AssertionError(f"Missing requirements. Looking for {module_names}, but found {module_lines}.")
    return module_lines


conda_build = os.path.basename(sys.argv[0]) in ('conda-build',  # unix
                                                'conda-build-script.py')  # win

setup_requires = setup_requirements(
    'etc/requirements_build.in',
    ('Cython', 'numpy'),
    conda_format=conda_build,
)

conditional_arguments = {
    'setup_requires' if not conda_build else 'build_requires': setup_requires,
}

if 'sdist' in sys.argv:
    with open('README.rst', mode="r", encoding="utf-8") as f:
        conditional_arguments['long_description'] = f.read()


setup(
    name='zipline',
    url="https://zipline.io",
    version=versioneer.get_version(),
    cmdclass=LazyBuildExtCommandClass(versioneer.get_cmdclass()),
    description='A backtester for financial algorithms.',
    entry_points={
        'console_scripts': [
            'zipline = zipline.__main__:main',
        ],
    },
    author='Quantopian Inc.',
    author_email='opensource@quantopian.com',
    packages=find_packages(include=['zipline', 'zipline.*']),
    ext_modules=ext_modules,
    include_package_data=True,
    package_data={root.replace(os.sep, '.'):
                  ['*.pyi', '*.pyx', '*.pxi', '*.pxd']
                  for root, dirnames, filenames in os.walk('zipline')
                  if '__pycache__' not in root},
    license='Apache 2.0',
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: Apache Software License',
        'Natural Language :: English',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Operating System :: OS Independent',
        'Intended Audience :: Science/Research',
        'Topic :: Office/Business :: Financial',
        'Topic :: Scientific/Engineering :: Information Analysis',
        'Topic :: System :: Distributed Computing',
    ],
    install_requires=install_requires(conda_format=conda_build),
    extras_require=extras_requires(conda_format=conda_build),
    **conditional_arguments
)
