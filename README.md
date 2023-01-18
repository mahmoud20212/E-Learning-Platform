# E-Learning-Platform

## Introduction
This is an E-Learning Platform content **management system (CMS)** project create using **Django**

## Deployment
### Clone the project
```
git clone https://github.com/mahmoud20212/E-Learning-Platform.git
```

### Run Project
### Run in production environment
- **This Project use Docker so you need install docker befor started run project**

- Run following command from project folder in the shell to start project:
```
docker compose up
```

- And run this command to migrations and creating a superuser:
```
docker compose exec web python /code/educa/manage.py migrate
```
```
docker compose exec web python /code/educa/manage.py createsuperuser
```

- And run this command to collecting static files:
```
docker compose exec web python /code/educa/manage.py collectstatic
```

### Run in local environment
- To run the project in local environment install (requirements.txt)

- And run this command:
```
python manage.py runserver --settings=educa.settings.local
```