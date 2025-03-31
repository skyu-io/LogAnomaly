from setuptools import setup, find_packages

setup(
    name="loganomaly",
    version="0.1.0",
    description="Semantic & Rule-based Log Anomaly Detection CLI + Dashboard",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Nilesh Jayanandana",
    author_email="nilesh@example.com",
    url="https://github.com/yourorg/loganomaly",
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
        "sentence-transformers",
        "scikit-learn",
        "drain3",
        "detect-secrets",
        "streamlit>=1.0"
    ],
    entry_points={
        "console_scripts": [
            "loganomaly=cli:cli"
        ]
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Intended Audience :: Developers",
        "Topic :: System :: Monitoring",
        "Topic :: Security"
    ],
    python_requires=">=3.8",
)
