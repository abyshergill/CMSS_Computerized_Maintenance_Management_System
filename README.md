# CMMS - Computerized Maintenance Management System

A Flask-based Computerized Maintenance Management System (CMMS) designed to track equipment status, manage maintenance logs, and monitor component lifecycles with expiry dates and image uploads.

## Features

- **Alert Tracking:** Monitor the status of components (Good, Alert, Bad) and receive notifications for upcoming maintenance.
- **Maintenance Logs:** Create and maintain a history of maintenance activities for each machine and component.
- **Expiry Date Management:** Track components with specific expiry dates to ensure timely replacements and inspections.
- **Image Uploads:** Upload and attach pictures to maintenance logs for visual verification and record-keeping.
- **Section & Component Management:** Organize equipment into sections for better categorization and management.
- **User Authentication:** Secure access with role-based permissions (Admin, Authorized).

## Prerequisites

Before you begin, ensure you have Python 3.8 or higher installed on your system.

## Getting Started

### 1. Clone the Repository

```bash
git clone <your-repository-url>
cd CMMS_Computerized_Management_System
```

### 2. Set Up a Virtual Environment

It is highly recommended to use a virtual environment to manage project dependencies.

#### On Windows:
```bash
python -m venv venv
venv\Scripts\activate
```

#### On macOS and Linux:
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

Once the virtual environment is activated, install the required packages:

```bash
pip install -r requirements.txt
```

### 4. Initialize the Database

The project uses Flask-Migrate for database management. Run the following commands to set up the local database:

```bash
flask db upgrade
```

*Note: This will create an `app.db` file (SQLite) in the root directory.*

## Running the Application

To start the development server, run:

```bash
python cmms.py
```

Or using Flask CLI:

```bash
export FLASK_APP=cmms.py
flask run
```
*(Use `set FLASK_APP=cmms.py` on Windows CMD or `$env:FLASK_APP = "cmms.py"` on PowerShell)*

The application will be available at `http://127.0.0.1:5000/`.

## How to Use the Application

1.  **Register/Login:** Create an account or log in to access the dashboard.
2.  **Manage Sections:** Start by creating "Sections" (e.g., "Engine Room", "Assembly Line") to group your components.
3.  **Add Components:** Inside each section, add components or machines. You can specify a unique ID, name, and an **expiry date**.
4.  **Monitor Alerts:** The dashboard or "Alert Hub" will show components that are in an "Alert" or "Bad" status based on their expiry dates or manually updated status.
5.  **Log Maintenance:**
    *   Navigate to a component's history or edit page.
    *   Add a maintenance entry with detailed notes.
    *   **Upload a picture** of the work performed or the part replaced.
6.  **Track History:** View the full maintenance history of any component to see past repairs and uploaded images.

## Project Structure

- `app/`: Main application package containing routes, models, and templates.
- `app/static/uploads/`: Directory where maintenance images are stored.
- `migrations/`: Database migration scripts.
- `cmms.py`: Main entry point for the application.
- `config.py`: Configuration settings for the Flask app.

## License

This project is licensed under the MIT License - see the LICENSE file for details (if applicable).
