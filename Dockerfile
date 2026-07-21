FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ARG NOTIFINHO_ICON_BASE_URL="https://raw.githubusercontent.com/FortPT/notifinho/main/assets/icons"
ENV NOTIFINHO_ICON_BASE_URL="${NOTIFINHO_ICON_BASE_URL}"

WORKDIR /notifinho

COPY requirements.txt /notifinho/requirements.txt

RUN pip install --no-cache-dir -r /notifinho/requirements.txt

COPY src /notifinho/src
COPY assets /notifinho/assets
COPY tools /notifinho/tools
COPY start.sh /notifinho/start.sh

RUN chmod +x /notifinho/start.sh

EXPOSE 8025 8080

CMD ["/notifinho/start.sh"]
