FROM python:3.10-slim as base

ARG PIP_EXTRA_INDEX_URL
ENV PYTHONFAULTHANDLER=1 \
    PYTHONHASHSEED=random \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/code

WORKDIR /code

FROM base as builder

ENV PIP_DEFAULT_TIMEOUT=100 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=1.2.2

RUN pip install -U setuptools pip wheel build "poetry==$POETRY_VERSION"
RUN python -m venv /venv

WORKDIR /code
COPY pyproject.toml poetry.lock /code/
RUN poetry export -f requirements.txt | /venv/bin/pip install -r /dev/stdin

COPY . .
RUN poetry build && /venv/bin/pip install dist/*.whl

FROM base as final
COPY --from=builder /venv /venv
ENTRYPOINT ["/venv/bin/python", "example.py"]
