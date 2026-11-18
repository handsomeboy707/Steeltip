FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home steeltip && chown -R steeltip:steeltip /app
USER steeltip
EXPOSE 8000
CMD ["python","-m","app.server","--live"]
