FROM node:22-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    COACH_ENV=production COACH_DATA_DIR=/data COACH_FRONTEND_DIR=/app/frontend/dist
WORKDIR /app
COPY backend/ ./backend/
RUN PYTHONPATH=backend python -m coach.repdb
RUN pip install --no-cache-dir ./backend tzdata
COPY --from=frontend /build/frontend/dist ./frontend/dist
EXPOSE 8000
CMD ["python", "-m", "coach.server"]
