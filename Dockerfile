FROM python:3.12-slim
WORKDIR /app
COPY server.py ./
COPY public ./public
ENV APP_ENV=production PYTHONUNBUFFERED=1
EXPOSE 3000
CMD ["python", "server.py"]
