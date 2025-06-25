#!/usr/bin/env python3
"""
SQL-Chat Setup Script
Intelligent Database Query Agent with DAG-based Query Decomposition
"""

from setuptools import setup, find_packages
import os

# Read the README file for long description
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

# Read requirements from requirements.txt
def read_requirements():
    requirements = []
    if os.path.exists("requirements.txt"):
        with open("requirements.txt", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    requirements.append(line)
    return requirements

setup(
    name="sql-chat",
    version="1.0.0",
    author="SQL-Chat Team",
    author_email="admin@example.com",
    description="Intelligent Database Query Agent with DAG-based Query Decomposition and Multi-threaded Execution",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/your-org/sql-chat",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Database",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=read_requirements(),
    extras_require={
        "gpu": ["faiss-gpu>=1.7.0"],
        "dev": [
            "pytest>=7.0.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "jupyter>=1.0.0",
        ],
        "viz": [
            "matplotlib>=3.7.0",
            "seaborn>=0.12.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "sql-chat-server=llm_rest_api:main",
            "sql-chat-sync=datahub_sync:main",
        ],
    },
    include_package_data=True,
    package_data={
        "": ["*.txt", "*.md", "*.json", "*.yaml", "*.yml"],
    },
    keywords="sql, database, ai, chatbot, dag, nlp, query-generation",
    project_urls={
        "Bug Reports": "https://github.com/your-org/sql-chat/issues",
        "Source": "https://github.com/your-org/sql-chat",
        "Documentation": "https://github.com/your-org/sql-chat/wiki",
    },
) 