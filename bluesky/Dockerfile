FROM python:3.12-alpine as build

RUN pip install --upgrade pip && pip install pipenv

WORKDIR /app

ENV PIPENV_VENV_IN_PROJECT=1

COPY Pipfile* /app/
RUN mkdir /app/.venv
RUN pipenv install --deploy


FROM python:3.12-alpine

RUN pip install --upgrade pip && pip install pipenv

WORKDIR /app

COPY . /app/
COPY --from=build /app/.venv /app/.venv

ENV PATH=/app/.venv/bin:$PATH

CMD ["pipenv", "run", "bot"]
