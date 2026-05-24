#!/bin/bash
sed -i 's/\r$//' /code/wait-for-it.sh
chmod +x /code/wait-for-it.sh
rm -f /code/educa/daphne.sock
exec /code/wait-for-it.sh db:5432 -- daphne -u /code/educa/daphne.sock educa.asgi:application
