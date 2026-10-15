FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install --no-cache-dir \
    pytest==8.3.5 \
    pytest-cov==6.1.1 \
    coverage==7.8.2 \
    hypothesis==6.131.9

RUN mkdir -p /bs /opt/deps

WORKDIR /bs
