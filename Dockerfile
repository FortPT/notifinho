FROM python:3.13.14-slim-bookworm@sha256:9d7f287598e1a5a978c015ee176d8216435aaf335ed69ac3c38dd1bbb10e8d64

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ARG NOTIFINHO_ICON_BASE_URL="https://raw.githubusercontent.com/FortPT/notifinho/main/assets/icons"
ENV NOTIFINHO_ICON_BASE_URL="${NOTIFINHO_ICON_BASE_URL}"

WORKDIR /notifinho

COPY requirements.txt /notifinho/requirements.txt

RUN apt-get update \
    && apt-get install --no-install-recommends -y cifs-utils nfs-common \
    && rm -rf /var/lib/apt/lists/* \
    && pip install \
    --disable-pip-version-check \
    --no-cache-dir \
    -r /notifinho/requirements.txt

COPY src /notifinho/src
COPY assets /notifinho/assets
COPY tools /notifinho/tools
COPY start.sh /notifinho/start.sh

RUN chmod +x /notifinho/start.sh

EXPOSE 8025 8080

CMD ["/notifinho/start.sh"]
