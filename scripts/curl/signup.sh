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
  "password": "SSelysium08!",
  "password_confirmation": "SSelysium08!"
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
  "password": "SSelysium08!",
  "password_confirmation": "SSelysium08!"
}
'
