FROM python:3.9-slim

RUN apt update && apt install gcc -y

COPY / /app/chatgpt-bot

WORKDIR /app/chatgpt-bot

RUN pip install -r requirements.txt

CMD [ "python", "src/main.py" ]