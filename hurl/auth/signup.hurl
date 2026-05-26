POST http://kvm-labs:8000/api/v1/auth/signup
accept: application/json
Content-Type: application/json
```
{
    "username": "{{username}}",
    "email": "{{email}}",
    "first_name": "{{first_name}}",
    "last_name": "{{last_name}}",
    "password": "{{password}}",
    "password_confirmation": "{{password_confirmation}}"
}
```

HTTP 201