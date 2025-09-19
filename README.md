"# server-client-ship" 
Run Offshore Proxy (Server)
docker run -d --name offshore -p 9999:9999 kartheek37/proxy-server:latest

Run Ship Proxy (Client)

docker run -d --name ship-proxy --link offshore:offshore -p 8080:8080 kartheek37/proxy-client:latest
Test with curl
For HTTP
curl -x http://localhost:8080 http://httpforever.com/

Source code (client + server + Dockerfiles):
https://github.com/nanivardhan2003/ship-proxy-assgnment

Offshore Proxy (Server):
https://hub.docker.com/repository/docker/kartheek37/proxy-server/general

Ship Proxy (Client):
https://hub.docker.com/repository/docker/kartheek37/proxy-client/general
