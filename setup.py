from setuptools import setup, find_packages

setup(
    name="biodiv-airflow",
    version="0.1.0",
    description="Biodiv shared modules for Composer DAGs (config, helpers, Dataflow flex template specs).",
    python_requires=">=3.11",
    packages=find_packages(include=["biodiv_airflow*"], exclude=["dags*"]),
    include_package_data=True,
    zip_safe=False,
    install_requires=[],
)
