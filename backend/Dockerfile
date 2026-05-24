FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi==0.115.0 uvicorn==0.30.6 boto3==1.35.0 python-dotenv==1.0.1 eth-account==0.13.4 requests==2.32.3

COPY . .

ENV PYTHONUNBUFFERED=1

EXPOSE 7860
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
