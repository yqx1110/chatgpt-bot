FROM python:3.9

COPY / /app/chatgpt-bot

WORKDIR /app/chatgpt-bot

RUN pip install -r requirements.txt

CMD [ "python", "src/main.py" ]