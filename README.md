# 「SIGNAL SHIFT」 Turf Management & Booking Platform API

A scalable, multi-tenant turf management and booking platform built with FastAPI, PostgreSQL, and a data-driven rules engine.

## Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL 16+
- Redis 7+
- Docker & Docker Compose (recommended)

### Using Docker Compose (recommended)

```bash
# Copy environment config
cp .env.example .env

# Start all services
docker-compose up -d

# Run migrations
docker-compose exec api alembic upgrade head

# API is available at http://localhost:8000
# Docs at http://localhost:8000/docs
```

### Local Development

```bash
# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -e ".[dev]"

# Copy and configure environment
cp .env.example .env
# Edit .env with your local DB/Redis settings

# Run migrations
alembic upgrade head

# Start dev server
uvicorn app.main:app --reload --port 8000
```

## Project Structure

```
signal-shift-api/
├── app/
│   ├── main.py              # FastAPI entrypoint
│   ├── config.py             # Settings (pydantic-settings)
│   ├── core/
│   │   ├── database.py       # SQLAlchemy async engine & session
│   │   ├── redis.py          # Redis pool & caching helpers
│   │   ├── security.py       # JWT & OTP utilities
│   │   ├── exceptions.py     # Exception hierarchy
│   │   ├── middleware.py      # RequestID, Timing, Tenant
│   │   ├── event_bus.py       # In-process pub-sub
│   │   └── pagination.py     # Offset & cursor pagination
│   ├── shared/
│   │   ├── types.py           # All StrEnum definitions
│   │   └── constants.py       # Non-configurable constants
│   ├── auth/                  # OTP → JWT authentication
│   ├── tenants/               # Multi-tenant management
│   ├── users/                 # User profiles & RBAC
│   ├── turfs/                 # Facility management & availability
│   ├── bookings/              # Booking lifecycle & pricing
│   ├── teams/                 # Team composition
│   ├── tournaments/           # Tournament lifecycle & rule engine
│   └── payments/              # Razorpay integration
├── alembic/                   # Database migrations
├── tests/
│   ├── unit/                  # Pure function tests
│   └── integration/           # API endpoint tests
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── .env.example
```

## API Endpoints

| Module       | Method | Endpoint                                        | Auth           |
|-------------|--------|-------------------------------------------------|----------------|
| **Auth**    | POST   | `/api/v1/auth/otp/send`                        | Public         |
|             | POST   | `/api/v1/auth/otp/verify`                      | Public         |
|             | POST   | `/api/v1/auth/refresh`                         | Public         |
| **Tenants** | POST   | `/api/v1/tenants/`                             | super_admin    |
|             | GET    | `/api/v1/tenants/`                             | super_admin    |
| **Users**   | GET    | `/api/v1/users/me`                             | Any            |
|             | PATCH  | `/api/v1/users/me`                             | Any            |
|             | PATCH  | `/api/v1/users/{id}/role`                      | super_admin    |
| **Turfs**   | POST   | `/api/v1/turfs/`                               | turf_admin     |
|             | GET    | `/api/v1/turfs/{id}/availability?target_date=` | Any            |
|             | POST   | `/api/v1/turfs/{id}/slot-rules`                | turf_admin     |
|             | POST   | `/api/v1/turfs/{id}/overrides`                 | turf_admin     |
| **Bookings**| POST   | `/api/v1/bookings/`                            | Any            |
|             | POST   | `/api/v1/bookings/preview-price`               | Any            |
|             | GET    | `/api/v1/bookings/my`                          | Any            |
|             | POST   | `/api/v1/bookings/{id}/cancel`                 | Owner/Admin    |
|             | PATCH  | `/api/v1/bookings/{id}/confirm`                | turf_admin     |
| **Teams**   | POST   | `/api/v1/teams/`                               | Any            |
|             | POST   | `/api/v1/teams/{id}/members`                   | Manager        |
| **Tournaments** | POST | `/api/v1/tournaments/`                        | turf_admin     |
|             | POST   | `/api/v1/tournaments/{id}/register`            | Manager        |
|             | GET    | `/api/v1/tournaments/{id}/standings`           | Any            |
|             | GET    | `/api/v1/tournaments/{id}/qualified`           | Any            |
|             | PATCH  | `/api/v1/tournaments/matches/{id}/result`      | turf_admin     |
| **Payments**| POST   | `/api/v1/payments/initiate`                    | Any            |
|             | POST   | `/api/v1/payments/webhook`                     | HMAC           |

## Key Architecture Decisions

- **Advisory Locking**: `pg_advisory_xact_lock(hash(turf_id + date))` prevents double-booking
- **Rules Engine**: Tournament qualification, pricing, cancellation — all JSONB-configurable
- **State Machines**: Explicit transition maps for Booking and Tournament lifecycles
- **CQRS Lite**: Standings are always computed, never stored (cached in Redis)
- **Safe Formula Eval**: AST-based evaluation for custom tournament formulas (never `eval()`)
- **Event Bus**: Decoupled side-effects via in-process pub-sub (upgrade path to message queues)

## Running Tests

```bash
# Unit tests (pure functions — no DB/Redis needed)
pytest tests/unit/ -v

# All tests
pytest -v --cov=app
```

## License

Proprietary — Signal Shift © 2026
