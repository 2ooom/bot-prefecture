FROM ubuntu:bionic

RUN apt-get update && apt-get install -y \
    python3 python3-pip

ENV APP_HOME /usr/src/app
WORKDIR /$APP_HOME

COPY *.py $APP_HOME/
COPY *.txt $APP_HOME/
COPY *.json $APP_HOME/

RUN pip3 install -r requirements.txt

ENV LC_ALL C.UTF-8
ENV LANG C.UTF-8
ENV PORT 8080
CMD env FLASK_APP=server.py flask run -p $PORT --host=0.0.0.0 --no-reload