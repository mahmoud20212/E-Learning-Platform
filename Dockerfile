# Pull official base Python Docker image
FROM python:3.10.6

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /code

# Install dependencies
RUN pip install --upgrade pip
COPY requirements.txt /code/
RUN pip install -r requirements.txt

# Copy the Django project
COPY . /code/

# Copy startup scripts to a location NOT overridden by the volume mount
COPY start-web.sh /usr/local/bin/start-web.sh
COPY start-daphne.sh /usr/local/bin/start-daphne.sh

# Fix CRLF and set execute permissions (immune to volume override)
RUN sed -i 's/\r$//' /usr/local/bin/start-web.sh /usr/local/bin/start-daphne.sh \
    && chmod +x /usr/local/bin/start-web.sh /usr/local/bin/start-daphne.sh
