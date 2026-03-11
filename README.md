# Landlord254 backend

This complete FastAPI backend provides:

    1. Database Models:

        - Landlord/Property/Unit/Tenant relationships

        - Payment tracking with receipts

        - Issue reporting system

        - Reminder system

    2. Africa's Talking Integration:

        - SMS service for reminders and notifications

        - USSD service with complete menu structure

        - Payment confirmation via USSD

        - Issue reporting via USSD

    3. n8n Integration:

        - Webhook triggers for all major events

        - Workflow automation for reminders

        - Issue notification workflows

    4. API Endpoints:

        - Full CRUD for properties, tenants, payments

        - Accounting and tax calculations

        - Dashboard statistics

        - Receipt generation

    5. USSD Menu:

        - *789*117# main menu

        - View Rent Balance

        - Confirm Payment

        - Contact Landlord with sub-menu for:

            i. Electrical/meter problem

            ii. Water problem

            iii. Financial discrepancies

            iv. Garbage disposal

            v. Other

## Quick Start

### Start the development server

```bash
uv run fastapi dev
```

Visit http://localhost:8000


## Project Structure

- `main.py` - FastAPI application entry point
- `pyproject.toml` - Project dependencies
