"""Small setuptools hooks: bundled native helper, independent of CPython ABI."""
from pathlib import Path
import runpy

from setuptools import Distribution, setup
from setuptools.command.build_py import build_py
from setuptools.command.bdist_wheel import bdist_wheel

build_native = runpy.run_path(str(Path(__file__).resolve().with_name("native_build.py")))["build_native"]
checks = runpy.run_path(str(Path(__file__).resolve().with_name("release_checks.py")))


class BuildPy(build_py):
    def run(self):
        super().run()
        build_native(Path(self.build_lib) / "macos_mediaremote" / "_native")


class Wheel(bdist_wheel):
    def finalize_options(self):
        super().finalize_options()
        self.root_is_pure = False

    def get_tag(self):
        _, lock = checks["read_configuration"]()
        return "py3", "none", checks["platform_tag"](lock)


class BinaryDistribution(Distribution):
    def has_ext_modules(self):
        # Select platlib even though the helper is not a CPython extension.
        return True


setup(distclass=BinaryDistribution, cmdclass={"build_py": BuildPy, "bdist_wheel": Wheel})
