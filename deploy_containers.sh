#!/usr/bin/env bash

docker stop host1
docker stop host2
docker stop host3
docker stop router1
docker stop router2
docker stop router3
docker stop router4
docker stop router5
docker rm router1
docker rm router2
docker rm router3
docker rm router4
docker rm router5
docker rm host1
docker rm host2
docker rm host3
docker network rm net1
docker network rm net2
docker network rm net3
docker network rm r1-r2
docker network rm r1-r3
docker network rm r2-r5
docker network rm r2-r4
docker network rm r3-r4
docker network rm r4-r5

docker network create --subnet=10.10.10.0/24 -d macvlan --internal net1
docker network create --subnet=20.20.20.0/24 -d macvlan --internal net2
docker network create --subnet=30.30.30.0/24 -d macvlan --internal net3
docker network create --subnet=192.168.1.0/29 -d macvlan --internal r1-r2
docker network create --subnet=192.168.1.8/29 -d macvlan --internal r1-r3
docker network create --subnet=192.168.1.16/29 -d macvlan --internal r2-r5
docker network create --subnet=192.168.1.24/29 -d macvlan --internal r3-r4
docker network create --subnet=192.168.1.32/29 -d macvlan --internal r2-r4
docker network create --subnet=192.168.1.40/29 -d macvlan --internal r4-r5

docker run -d --name host1 -h host1 --cap-add=NET_ADMIN host
docker network connect --ip 10.10.10.2 net1 host1

docker run -d --name host2 -h host2 --cap-add=NET_ADMIN host
docker network connect --ip 20.20.20.2 net2 host2

docker run -d --name host3 -h host3 --cap-add=NET_ADMIN host
docker network connect --ip 30.30.30.2 net3 host3

docker run -d --name router1 -h router1 --cap-add=NET_ADMIN router
docker run -d --name router2 -h router2 --cap-add=NET_ADMIN router
docker run -d --name router3 -h router3 --cap-add=NET_ADMIN router
docker run -d --name router4 -h router4 --cap-add=NET_ADMIN router
docker run -d --name router5 -h router5 --cap-add=NET_ADMIN router

# Router 1 networking
docker network connect --ip 10.10.10.254 net1 router1
docker network connect --ip 192.168.1.2 r1-r2 router1
docker network connect --ip 192.168.1.10 r1-r3 router1

# Router 2 networking
docker network connect --ip 192.168.1.3 r1-r2 router2
docker network connect --ip 192.168.1.18 r2-r5 router2
docker network connect --ip 192.168.1.34 r2-r4 router2

# Router 3 networking
docker network connect --ip 192.168.1.11 r1-r3 router3
docker network connect --ip 192.168.1.26 r3-r4 router3

# Router 4 networking
docker network connect --ip 192.168.1.27 r3-r4 router4
docker network connect --ip 192.168.1.35 r2-r4 router4
docker network connect --ip 192.168.1.42 r4-r5 router4
docker network connect --ip 30.30.30.254 net3 router4

# Router 5 networking
docker network connect --ip 192.168.1.19 r2-r5 router5
docker network connect --ip 192.168.1.43 r4-r5 router5
docker network connect --ip 20.20.20.254 net2 router5


# Cleanup any default gw by docker
docker exec -ti host1 bash -c "route del default gw 172.17.0.1"
docker exec -ti host2 bash -c "route del default gw 172.17.0.1"
docker exec -ti host3 bash -c "route del default gw 172.17.0.1"
docker exec -ti host1 bash -c "route add default gw 10.10.10.254"
docker exec -ti host2 bash -c "route add default gw 20.20.20.254"
docker exec -ti host3 bash -c "route add default gw 30.30.30.254"
docker exec -ti router1 bash -c "route del default gw 172.17.0.1"
docker exec -ti router2 bash -c "route del default gw 172.17.0.1"
docker exec -ti router3 bash -c "route del default gw 172.17.0.1"
docker exec -ti router4 bash -c "route del default gw 172.17.0.1"
docker exec -ti router5 bash -c "route del default gw 172.17.0.1"
