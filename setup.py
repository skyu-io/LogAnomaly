from setuptools import setup, find_packages

setup(
    name="loganomaly",
    version="0.1.2",
    description="Advanced Log Anomaly Detection with AI and Interactive Dashboard",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Nilesh Jayanandana",
    author_email="nilesh93.j@gmail.com",
    url="https://github.com/skyu-io/LogAnomaly",
    packages=find_packages(include=["loganomaly", "loganomaly.*"]),
    include_package_data=True,
    py_modules=['cli'],
    install_requires=[
        "click>=8.0",
        "pandas>=1.0",
        "aiohttp>=3.8",
        "tqdm>=4.0",
        "tiktoken",
        "pyyaml>=6.0",
        "numpy>=1.21",
        "sentence-transformers>=2.2.0",
        "scikit-learn>=1.0.0",
        "drain3>=0.9.6",
        "detect-secrets>=1.0.0",
        "streamlit>=1.0",
        "plotly>=6.0.0",
        "asyncio>=3.4.3",
        "tenacity>=8.0.0",
        "python-dateutil>=2.8.0",
        "scipy>=1.7.0"
    ],
    entry_points={
        "console_scripts": [
            "loganomaly=cli:cli"
        ]
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "Intended Audience :: Information Technology",
        "Topic :: System :: Monitoring",
        "Topic :: System :: Logging",
        "Topic :: Security",
        "Topic :: Scientific/Engineering :: Artificial Intelligence"
    ],
    keywords="logs, anomaly detection, security, monitoring, ai, llm, dashboard",
    python_requires=">=3.8",
    project_urls={
        "Bug Reports": "https://github.com/skyu-io/LogAnomaly/issues",
        "Source": "https://github.com/skyu-io/LogAnomaly",
        "Documentation": "https://github.com/skyu-io/LogAnomaly/blob/main/README.md"
    },
)
