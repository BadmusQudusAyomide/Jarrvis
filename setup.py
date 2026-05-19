from setuptools import setup

setup(
    name="jarvis-cli",
    version="1.0",
    py_modules=["jarvis_cli"],
    install_requires=["requests"],
    entry_points={
        "console_scripts": [
            "jarvis=jarvis_cli:main",
        ],
    },
)
