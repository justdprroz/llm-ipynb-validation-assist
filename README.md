# GradeLab

Сервис GradeLab разработан в рамках проекта "Проверка тетрадок в AnyTask с помощью LLM"

## Запуск сервиса

```bash
cd gradelab
cp .env.example .env
docker compose up --build
```

- UI: http://localhost:3000  
- API: http://localhost:8000  
- Grafana: http://localhost:3001 (`admin` / `GRAFANA_ADMIN_PASSWORD`)  
- MinIO console: http://localhost:9001