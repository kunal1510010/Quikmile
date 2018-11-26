FROM python:3.6

ADD . /gps-server

WORKDIR /gps-server

RUN pip install -r requirements.txt

EXPOSE 5000:5100

CMD ["python", "-m","server.run"]