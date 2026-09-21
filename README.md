# AI-Powered Dental Management System

A working Django implementation of the *AI-Powered Dental Management System for
Smart Patient Care* synopsis: a web application that runs a dental clinic's
day-to-day operations — patients, dentists, appointments, treatments,
prescriptions, billing and reporting — with an AI assistant layered on top for
patient support and clinical decision support.

Three roles, three dashboards: **administrator**, **dentist** and **patient**.

---

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env          # optional, every value has a working default
python manage.py migrate
python manage.py seed_demo    # realistic demo clinic
python manage.py runserver
```

Open <http://127.0.0.1:8000/>.

### Demo accounts

`seed_demo` creates a full clinic. The password for every account is
**`dental123`**.

| Role | Username | What you see |
|---|---|---|
| Administrator | `clinicadmin` | Clinic-wide dashboard, reports, staff and billing |
| Dentist | `anita.rao` | Own diary, patient records, AI briefings |
| Dentist | `vikram.shah`, `priya.nair`, `rahul.mehta` | Other specializations |
| Patient | `arjun.patel` | Own appointments, records, bills, AI tools |
| Patient | 11 more — see the patient list | Varied histories and risk factors |

To wipe and regenerate: `python manage.py seed_demo --flush`.

For the Django admin, create a superuser: `python manage.py createsuperuser`.

---

## Enabling the Gemini API

**The AI features work out of the box with no API key.** Without one, they are
served by a bundled rule-based dental engine — real FAQ answers, real symptom
triage, real care plans — so the whole system is demonstrable offline and at
zero cost.

To switch to the Gemini API, get a key from
[Google AI Studio](https://aistudio.google.com/apikey) and put it in `.env`:

```ini
GEMINI_API_KEY=...
AI_MODEL=gemini-3.6-flash
```

Restart the server. The AI usage page (**Manage → AI usage log**, administrator
only) shows which engine is answering, plus tokens, latency and failures.

`AI_EFFORT` controls how much the model thinks before answering: `low` (the
default) disables thinking for the fastest, cheapest replies, `medium` and
`high` let the model decide. `AI_THINKING_BUDGET` overrides that with an exact
token budget if you need finer control.

The rule engine stays in place as a fallback: if the API is unreachable, rate
limited, misconfigured or returns something unusable, the request falls back
automatically and the user still gets an answer. That behaviour is covered by
tests.

---

## The AI features

| Feature | Where | What it does |
|---|---|---|
| **Dental chat assistant** | `/assistant/` | Conversational answers about teeth, gums, procedures and using the system. Threaded history, live typing indicator, no page reload. |
| **Symptom checker** | `/assistant/symptom-checker/` | Turns reported symptoms into possible areas of concern, an urgency level (Routine / Soon / Urgent / Emergency), self-care advice and a pre-filled booking link. |
| **Personalized care plan** | `/assistant/care-plan/` | A daily routine, diet guidance and warning signs built from that patient's own habits, medical history and recent treatment. |
| **Clinical pre-visit briefing** | Dentist's diary → robot icon | Compresses a patient's record into a short briefing before the dentist walks into the room. Decision support only. |
| **Urgency alerts** | Administrator dashboard | An Urgent or Emergency triage result raises an in-app alert for the clinic. |
| **AI usage log** | `/assistant/logs/` | Every AI call: feature, engine, tokens, latency, success. |

### Clinical safety

The synopsis is explicit that the AI assists and the dentist decides, so that is
enforced in the code rather than left to the prompt alone:

- The system prompt forbids diagnosis and prescribing, and requires an
  immediate-care warning for red-flag symptoms.
- Every patient-facing AI output carries a visible "not a diagnosis" disclaimer.
- Urgency is **escalated, never de-escalated**, by swelling, fever, difficulty
  swallowing, high pain scores and red-flag phrases in free text. Swelling with
  fever, or any difficulty swallowing, is always an emergency.
- Structured outputs constrain the model to a fixed schema, and the response is
  validated again server-side before it reaches the database.
- The emergency banner and clinic phone number are shown before the form, not
  after the result.

---

## What is implemented

**Patients** — self-registration, profile with medical history, allergies,
medication and oral-hygiene habits, appointment booking and cancellation,
treatment and prescription history, invoices, notifications, all three AI tools.

**Dentists** — day diary with free-slot view, weekly working hours and leave,
patient records, diagnosis and treatment entry, prescriptions with multiple
medicines, follow-up scheduling, AI pre-visit briefings.

**Administrators** — clinic dashboard, patient and staff management, booking on
a patient's behalf, invoicing with discounts, tax and part-payments, reports,
AI usage monitoring, Django admin.

**Appointments** — slots are generated from each dentist's working hours in
their own slot length, minus existing bookings, leave and a minimum-notice
window. Double-booking is prevented both by re-checking inside the transaction
and by a database constraint, so two people clicking at once cannot collide.

**Billing** — itemised invoices, discount before tax, part-payments, automatic
status (Unpaid → Partial → Paid), printable invoice, overpayment rejected.

**Notifications** — in-app for booking, confirmation, cancellation, treatment,
prescription, invoice and payment; email for reminders.

---

## Reminders

`send_reminders` sends appointment reminders and follow-up reminders. It is
idempotent — each is sent once — so it is safe to run on a schedule.

```bash
python manage.py send_reminders                      # 24h ahead, plus follow-ups
python manage.py send_reminders --hours 48           # wider window
python manage.py send_reminders --dry-run            # show what would be sent
python manage.py send_reminders --no-email           # in-app notifications only
```

Email goes to the console by default. Configure SMTP in `.env` to send for real.

Schedule it hourly with cron, or Windows Task Scheduler:

```
schtasks /create /tn "Dental reminders" /tr "C:\path\to\python.exe C:\path\to\manage.py send_reminders" /sc hourly
```

---

## Testing

```bash
python -m pytest
```

150 tests covering booking rules (slot generation, double-booking, leave,
rescheduling, minimum notice), billing arithmetic and payment states, clinical
record workflow, role permissions for all three roles, the AI rule engine's
triage decisions, the Gemini request/response handling, and the fallback path
when the API fails. Tests never call the real API.

Every page is also covered by a render test for each role that may open it.

---

## Architecture

```
Browser (Bootstrap 5 + vanilla JS)
      |
      |  HTML pages          JSON (chat, free slots)
      v                              v
Django views / forms  <-->  Django REST Framework
      |
      +-- appointments/services.py   slot generation, booking rules
      +-- aiassistant/services/
      |       assistant.py           facade: try Gemini, fall back, log
      |       gemini_provider.py     Google Gen AI SDK, structured outputs
      |       rule_engine.py         offline triage, FAQ, care plans
      |       knowledge.py           curated dental knowledge base
      +-- notifications/services.py  in-app + email
      |
      v
  ORM -> SQLite (default) / PostgreSQL / MySQL
```

| App | Responsibility |
|---|---|
| `accounts` | Custom `User` with roles, patient and dentist profiles |
| `appointments` | Availability, leave, slots, appointments |
| `records` | Dental history, treatments, prescriptions |
| `billing` | Invoices, line items, payments |
| `aiassistant` | Chat, symptom triage, care plans, AI audit log |
| `notifications` | In-app and email notifications |
| `core` | Dashboards, reports, permissions, management commands |

### Stack

Django 5.2 · Django REST Framework · Google Gen AI SDK · Bootstrap 5 ·
SQLite / PostgreSQL / MySQL · WhiteNoise · pytest.

The synopsis proposed React and Node.js; this is built in Django as requested,
so the templating and REST layers replace the React front end and Express API.
Everything else — the modules, the database design, the AI integration and the
three-layer architecture — follows the synopsis.

---

## Using PostgreSQL or MySQL

Set `DATABASE_URL` in `.env` and install the driver:

```ini
DATABASE_URL=postgres://user:password@localhost:5432/dental
# or
DATABASE_URL=mysql://user:password@localhost:3306/dental
```

```bash
pip install "psycopg[binary]"    # PostgreSQL
pip install mysqlclient          # MySQL
python manage.py migrate
```

---

## Deploying

```ini
# .env
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=<50+ random characters>
DJANGO_ALLOWED_HOSTS=your-domain.com
DATABASE_URL=postgres://...
```

```bash
python manage.py collectstatic --noinput
python manage.py migrate
gunicorn config.wsgi:application        # or waitress-serve on Windows
```

With `DEBUG=False`, HTTPS redirect, HSTS, secure cookies and the other
production security settings switch on automatically; `manage.py check --deploy`
passes. Static files are hashed and compressed by WhiteNoise.

One thing to know: `collectstatic` and the web server must agree on
`DJANGO_HASHED_STATIC`. Keeping it in `.env` (rather than passing it on the
command line) guarantees they do — otherwise the server 500s on a missing
manifest entry.

### Render

`render.yaml` is a blueprint for a free web service plus a free PostgreSQL
database. From the Render dashboard: **New > Blueprint**, pick this repo, and
Render reads the file. `build.sh` installs dependencies, runs `collectstatic`
and applies migrations on every deploy.

`DJANGO_SECRET_KEY` is generated by Render; `GEMINI_API_KEY` is marked
`sync: false`, so set it in the dashboard (leave it blank to run on the
rule-based engine). The `*.onrender.com` hostname is picked up from
`RENDER_EXTERNAL_HOSTNAME` at runtime, so only custom domains need to go in
`DJANGO_ALLOWED_HOSTS`.

After the first deploy, create a login from the service's **Shell** tab:

```bash
python manage.py createsuperuser
python manage.py seed_demo       # optional demo data
```

Two caveats on the free plan: the service sleeps after 15 minutes idle and
takes ~a minute to wake, and the free database expires after 30 days. Uploads
would not survive a restart either -- the app stores no media files today, so
adding any would mean adding S3 or a Render disk first.

---

## Notes and limitations

- AI answers are general information, not diagnosis; the dentist decides.
- The rule engine covers common dental complaints, not rare presentations.
- The Gemini API needs internet access and an API key; without one the offline
  engine is used.
- Payments are recorded by staff — no payment gateway is integrated.
- X-ray image analysis, voice input, tele-dentistry and a mobile app are future
  scope, as in the synopsis.
