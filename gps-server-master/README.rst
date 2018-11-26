Run following command to start server -

python -m server.run

To build docker image -

docker run -i -t gps-server

Run Docker Image -

docker run -i -t -p 5000-5010:5000-5010/tcp  gps-server