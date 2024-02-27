FROM python:3.11-alpine

COPY . /app
WORKDIR /app

RUN apk add --no-cache build-base

RUN pip install --no-cache-dir pipenv
RUN pipenv install --deploy

RUN pip cache purge
RUN pipenv --clear

RUN apk del build-base
RUN apk add --no-cache libstdc++
