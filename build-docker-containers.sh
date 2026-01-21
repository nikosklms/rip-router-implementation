#!/usr/bin/env bash

docker build -t host -f Dockerfile_host .

docker build -t router -f Dockerfile_router .
