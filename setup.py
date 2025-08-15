"""
Setup script for the Immich Auto-Tagger package.
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read the README file
readme_path = Path(__file__).parent / "README.md"
long_description = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""

# Read requirements
requirements_path = Path(__file__).parent / "requirements.txt"
requirements = []
if requirements_path.exists():
    requirements = [
        line.strip() 
        for line in requirements_path.read_text().splitlines() 
        if line.strip() and not line.startswith("#")
    ]

setup(
    name="immich-tagger",
    version="1.0.0",
    description="AI-powered image tagging service for Immich",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Immich Auto-Tagger Team",
    author_email="your-email@example.com",
    url="https://github.com/your-username/immich-booru-tagger",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Multimedia :: Graphics",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    python_requires=">=3.11",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "black>=23.0.0",
            "isort>=5.12.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "immich-tagger=immich_tagger.main:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
    keywords="immich, ai, tagging, anime, image-recognition, machine-learning",
    project_urls={
        "Bug Reports": "https://github.com/your-username/immich-booru-tagger/issues",
        "Source": "https://github.com/your-username/immich-booru-tagger",
        "Documentation": "https://github.com/your-username/immich-booru-tagger#readme",
    },
)
