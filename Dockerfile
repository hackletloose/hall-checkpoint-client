FROM python:alpine

WORKDIR /code

RUN pip install requests aiohttp aio_pika python-dotenv

COPY ./* /code/
RUN chmod +x /code/entrypoint.sh

ENTRYPOINT ["/code/entrypoint.sh"]
