"""
Setup script for jury-judge-worker package
"""
from setuptools import setup, find_packages

setup(
    name="jury-judge-worker",
    version="0.1.0",
    description="AI Agent evaluation framework using AISI Inspect criteria",
    packages=find_packages(),
    python_requires=">=3.11",
    install_requires=[
        "inspect-ai>=0.3.142",
        "inspect-evals>=0.3.102",
        "openai>=1.82.0",
        "anthropic>=0.39.0",
        "google-adk>=1.0.0",
        "weave>=0.51.0",
    ],
)
