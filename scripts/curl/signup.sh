#!/usr/bin/env bash

curl -X 'POST' \
    'http://kvm-labs:8000/api/v1/auth/signup' \
    -H 'accept: application/json' \
    -H 'Content-Type: application/json' \
    -D - \
    -o >(jq .) \
    -s \
    -d '{
  "username": "tiago_prof",
  "email": "tiagoprn+professional@gmail.com",
  "first_name": "tiago",
  "last_name": "lima (professional)",
  "password": "!DoBett3R!",
  "password_confirmation": "!DoBett3R!"
}
' \
    && curl -X 'POST' \
        'http://kvm-labs:8000/api/v1/auth/signup' \
        -H 'accept: application/json' \
        -H 'Content-Type: application/json' \
        -D - \
        -o >(jq .) \
        -s \
        -d '{
  "username": "tiago",
  "email": "tiagoprn+personal@gmail.com",
  "first_name": "tiago",
  "last_name": "lima",
  "password": "!DoBett3R!",
  "password_confirmation": "!DoBett3R!"
}
'
