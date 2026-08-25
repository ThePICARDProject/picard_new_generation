# PICARD

PICARD is a web application for running Apache Spark experiments. Team members can upload CSV datasets and Python or JAR algorithms, combine them into experiments, and follow each run from the browser.

The application has a React frontend, a Django API, a Celery worker, and a small Spark cluster. MySQL stores application data and Redis carries work from Django to Celery. Docker Compose runs the full stack locally.

## Getting started

The PICARD Docker Compose system is already running on the PICARD backend machine. The setup below creates a local development environment on your computer. Changes to your local configuration do not affect the running PICARD system.

You will need Git, Docker, and Docker Compose. Docker Desktop includes Compose.

1. Clone the repository and enter this directory.

2. Create your local backend configuration:

   ```bash
   cp backend/.env.example backend/.env
   ```

3. Open `backend/.env` and create new credentials for your local environment. These are not existing project credentials that you need to find. Choose a new local database password and use it for both `DB_PASSWORD` and `MYSQL_ROOT_PASSWORD`.

   Generate a Django secret with:

   ```bash
   python3 -c "from secrets import token_urlsafe; print(token_urlsafe(50))"
   ```

   Copy the output into `DJANGO_SECRET_KEY`. If Python 3 is not installed locally, a password manager can generate a long random value instead. Keep these values in `backend/.env` and do not commit that file.

4. Build and start the application:

   ```bash
   docker compose up --build
   ```

The first build can take a few minutes while the backend and Spark images install their dependencies. Django applies database migrations as the backend starts.

Once the services are ready, open:

- Application: <http://localhost:3000>
- Django API: <http://localhost:5000>
- Spark master UI: <http://localhost:8080>
- Spark worker UI: <http://localhost:8081>

Stop the stack with `Ctrl+C`, followed by:

```bash
docker compose down
```

## Working in the repository

- `frontend/` contains the React and Vite application.
- `backend/` contains the Django API and the Celery task that submits Spark jobs.
- `backend/datasets/`, `backend/scripts/`, and `backend/experiments/` contain the main application models and endpoints.
- `spark-cluster/` defines the Spark master and worker image.
- `docker-compose.yml` connects the application services and their shared storage.

Backend source is mounted into its container, so Django reloads as Python files change. The frontend is built into its image. Rebuild that service after changing frontend code:

```bash
docker compose up --build frontend
```

Useful checks before opening a pull request are:

```bash
docker compose exec backend python manage.py check
cd frontend
npm install
npm run lint
npm run build
```

For architecture notes, team practices, and the rest of the project documentation, visit the [PICARD onboarding page](https://thepicardproject.github.io/Onboarding-Page/).
