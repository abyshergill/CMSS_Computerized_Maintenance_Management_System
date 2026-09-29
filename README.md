# CMMS - Computerized Maintenance Management System

A Django-based Computerized Maintenance Management System for tracking equipment status, maintenance history, component expiry dates, alerts, and controlled maintenance uploads.

## Features

- **Alert Tracking:** Monitor the status of components (Good, Alert, Bad) and receive notifications for upcoming maintenance.
- **Maintenance Logs:** Create and maintain a history of maintenance activities for each machine and component.
- **Expiry Date Management:** Track components with specific expiry dates to ensure timely replacements and inspections.
- **Image Uploads:** Upload and attach pictures to maintenance logs for visual verification and record-keeping.
- **Section & Component Management:** Organize equipment into sections for better categorization and management.
- **User Authentication:** Secure access with role-based permissions (Admin, Authorized).

## Prerequisites

Python 3.12 or higher is recommended. This repository uses the existing `virtual_cmss` environment on macOS/Linux.

## Getting Started

### 1. Clone the Repository

```bash
git clone git@github.com:abyshergill/CMSS_Computerized_Maintenance_Management_System.git
cd CMSS_Computerized_Maintenance_Management_System
```

### 2. Set Up a Virtual Environment

It is highly recommended to use a virtual environment to manage project dependencies.

```bash
source virtual_cmss/bin/activate
pip install -r requirements.txt
```

### 3. Initialize the Django Database

```bash
export DJANGO_DEBUG=1
export DJANGO_SECRET_KEY='local-development-secret-change-me'
python manage.py migrate
```

## Running the Application

Start the Django development server with:

```bash
python manage.py runserver
```

### Recurring Preventive Maintenance

Admins can create daily, weekly, monthly, or yearly jobs from **Recurring jobs** in the navigation. Choose the local time and IANA timezone; work orders are generated the selected number of days ahead. Exclude weekdays, calendar days, months, or one-time dates; a match skips that occurrence without shifting it, while the schedule continues at its next normal interval. Monthly days beyond a month's length use its final day, and February 29 schedules use February 28 in non-leap years. Pausing a schedule does not remove previously generated work orders.

To generate scheduled work orders automatically, run this Django command every minute using cron, launchd, or your deployment scheduler:

```bash
./virtual_cmss/bin/python manage.py generate_preventive_work_orders
```

The command is safe to run repeatedly; a database uniqueness constraint prevents duplicate work orders for a schedule occurrence. For local testing, it can be run manually; recurring jobs will not generate automatically unless this command is scheduled.

## How to Use the Application

1.  **Register/Login:** Log in with a Django user. An administrator can register additional users.
2.  **Manage Sections:** Start by creating "Sections" (e.g., "Engine Room", "Assembly Line") to group your components.
3.  **Add Components:** Inside each section, add components or machines. You can specify a unique ID, name, and an **expiry date**.
4.  **Monitor Alerts:** The dashboard or "Alert Hub" will show components that are in an "Alert" or "Bad" status based on their expiry dates or manually updated status.
5.  **Log Maintenance:**
    *   Navigate to a component's history or edit page.
    *   Add a maintenance entry with detailed notes.
    *   **Upload a picture** of the work performed or the part replaced.
6.  **Track History:** View the full maintenance history of any component to see past repairs and uploaded images.

## Legacy Data Import

Import the existing Flask SQLite database without modifying it:

```bash
python manage.py import_legacy --database app.db --dry-run
python manage.py import_legacy --database app.db
```

The import is idempotent by legacy primary key. Imported users receive unusable Django passwords because Werkzeug hashes are not automatically portable; issue password resets before production use.

## Security and Validation

The Django app uses ORM queries, CSRF middleware, POST-only state changes, role checks, secure cookies, environment-provided secrets, password validation, escaped templates, upload size/signature checks, and transactional component updates.

```bash
DJANGO_DEBUG=1 python manage.py test cmms
DJANGO_DEBUG=1 python manage.py check
python -m pytest -q
```

For deployment, set `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, HTTPS, HSTS, and a production database/media storage policy explicitly.

## Project Structure

- `cmms/`: Django application containing models, forms, views, services, migrations, and tests.
- `config/`: Django settings, URL configuration, WSGI, and ASGI entry points.
- `templates/`: Django templates.
- `manage.py`: Django management entry point.
- `app/` and `migrations/`: Legacy Flask implementation retained for reference and data import.

## License

This project is licensed under the MIT License - see the LICENSE file for details (if applicable).
