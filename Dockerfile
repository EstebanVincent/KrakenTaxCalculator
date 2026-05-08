FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN mkdir -p /app
ADD . /app
WORKDIR /app
RUN uv sync --frozen

# Set environment variables for production
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
# LOCAL = persist all data to mounted volume; CLOUD = only persist prices
ENV APP_ENV=LOCAL

RUN chmod u+x scripts/init.sh

EXPOSE 8501
CMD ["scripts/init.sh"]
