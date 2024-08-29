FROM python:alpine

WORKDIR /code

RUN pip install aiohttp aio_pika python-dotenv

COPY ./ban_client.py /code/ban_client.py
COPY ./entrypoint.sh /code/

ENTRYPOINT ["/code/entrypoint.sh"]
