FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /notifinho

COPY requirements.txt /notifinho/requirements.txt

RUN pip install --no-cache-dir -r /notifinho/requirements.txt

COPY src /notifinho/src
COPY tools /notifinho/tools
COPY start.sh /notifinho/start.sh

RUN chmod +x /notifinho/start.sh

EXPOSE 8025

CMD ["/notifinho/start.sh"]
