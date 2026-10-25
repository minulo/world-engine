# The world engine in a container: one way that runs the same on Linux, macOS (Apple silicon and Intel) and Windows.
#
#   docker build -t worldengine .
#   docker run --rm -p 127.0.0.1:8765:8765 -v worldengine-worlds:/app/worlds worldengine
#
# then open http://localhost:8765/ . The first start builds the preview world into the volume worldengine-worlds
# (one to two minutes); later starts serve it at once. `docker compose up` does the same (compose.yaml).
# The base image names Python 3.13, for which requirements.lock was made; its patch release and Debian base are those
# of the day the image is built (3.13.17 on Debian 13 in October 2026). Another can be named, for a fixed patch release
# or a mirror of Docker Hub: docker build --build-arg PYTHON_IMAGE=mirror.gcr.io/library/python:3.13-slim .
ARG PYTHON_IMAGE=python:3.13-slim
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ROOT_USER_ACTION=ignore \
    NUMBA_CACHE_DIR=/home/worldengine/.cache/numba

WORKDIR /app
# The pinned packages first, so that a change of the code does not download them again.
COPY requirements.lock ./
RUN pip install --only-binary=:all: -r requirements.lock

COPY pyproject.toml ./
COPY src ./src
COPY data ./data
COPY viewer ./viewer
COPY scripts/docker-start.sh /usr/local/bin/worldengine-start
RUN pip install --no-deps -e . \
 && chmod 755 /usr/local/bin/worldengine-start \
 && useradd --create-home --uid 1000 worldengine \
 && mkdir -p /app/worlds /home/worldengine/.cache/numba \
 && chown worldengine:worldengine /app/worlds /home/worldengine/.cache/numba

USER worldengine
VOLUME /app/worlds
EXPOSE 8765
ENTRYPOINT ["worldengine-start"]
