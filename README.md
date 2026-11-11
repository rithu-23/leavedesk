# LeaveDesk

LeaveDesk is an employee leave-management app, built step by step during the AYPOLS Enablement Workshop.

- **Day 1 (current):** a written specification (`SPEC.md`) and a plain-Python domain package with the leave rules. No web framework or database yet.
- **Day 2:** a tested REST API with FastAPI.
- **Day 3:** storage on PostgreSQL.
- **Day 4:** an Angular front end.

## Requirements

- Python 3.12 or newer
- Git

## Setup (macOS / Linux)

```bash
# 1. Download the project
git clone https://github.com/rithu-23/leavedesk.git
cd leavedesk

# 2. Create and switch on a virtual environment (a private Python for this project)
python3.12 -m venv .venv
source .venv/bin/activate

# 3. Install the libraries listed in requirements.txt
pip install -r requirements.txt
```

## Run the demo

```bash
python -m leavedesk.demo
```

The demo runs the normal leave flow (apply, approve, notify) and every edge case from the spec, printing the result of each.

## Project structure

| Path | What it holds |
|---|---|
| `leavedesk/domain/exceptions.py` | Custom errors: `LeaveDeskError` and its subclasses |
| `leavedesk/domain/models.py` | Pydantic models and enums |
| `leavedesk/domain/dates.py` | Working-day count and overlap check |
| `leavedesk/domain/balance.py` | `LeaveBalance` dataclass |
| `leavedesk/domain/policies.py` | Abstract `LeavePolicy` and leave-type policies |
| `leavedesk/domain/repository.py` | Storage interface and in-memory store |
| `leavedesk/domain/instrumentation.py` | `@audit` decorator and timing context manager |
| `leavedesk/domain/notifications.py` | Notifier classes and concurrent sending |
| `leavedesk/domain/service.py` | `LeaveService`: apply, approve, reject, cancel |
| `leavedesk/demo.py` | Runs the full flow and all edge cases |
| `SPEC.md` | Specification and acceptance criteria |
| `AI_NOTES.md` | Log of AI assistance and what was checked or fixed |
| `requirements.txt` | Exact library versions |
