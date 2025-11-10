"""Setup script for self-reflexive-orchestrator."""

from pathlib import Path

from setuptools import find_packages, setup

# Read README for long description
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text() if readme_file.exists() else ""

setup(
    name="self-reflexive-orchestrator",
    version="0.1.0",
    description="Autonomous coding agent for GitHub workflow automation",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Your Name",
    author_email="your.email@example.com",
    url="https://github.com/yourusername/self-reflexive-orchestrator",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.9",
    install_requires=[
        "anthropic>=0.39.0",
        "pyyaml>=6.0.1",
        "python-dotenv>=1.0.0",
        "PyGithub>=2.1.1",
        "gitpython>=3.1.40",
        "click>=8.1.7",
        "rich>=13.7.0",
        "python-dateutil>=2.8.2",
        "redis>=5.0.1",
        "httpx>=0.25.2",
        "structlog>=24.1.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.3",
            "pytest-asyncio>=0.21.1",
            "pytest-mock>=3.12.0",
            "pytest-cov>=4.1.0",
            "black>=23.12.1",
            "ruff>=0.1.9",
            "mypy>=1.7.1",
        ],
    },
    entry_points={
        "console_scripts": [
            "orchestrator=cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Version Control :: Git",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
