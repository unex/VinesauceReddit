FROM python:3.11-alpine

COPY . /app
WORKDIR /app

RUN apk add build-base git

RUN pip install pipenv
RUN pipenv install --system --deploy

RUN pip cache purge
RUN pipenv --clear

RUN apk del build-base git
RUN apk cache clean

CMD ["pipenv"]
