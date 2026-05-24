#!/bin/bash
sed -i 's/\r$//' /code/wait-for-it.sh
chmod +x /code/wait-for-it.sh
exec /code/wait-for-it.sh db:5432 -- uwsgi --ini /code/config/uwsgi/uwsgi.ini
