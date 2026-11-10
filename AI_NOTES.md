# AI Usage Notes

**Tool used:** Claude (claude.ai)
**How I use it:** I ask for step-by-step instructions and code, then read every line, run it, and check the result before committing. Anything I change, and why, is logged below.

---

## Entry 1 — Project setup (Day 1)

**Prompt:** Set up a Python 3.12+ project for LeaveDesk on macOS with a virtual environment, Pydantic v2, a .gitignore and a README.

**Generated:** Terminal commands (version checks, `git init`, venv creation, `pip install`), plus the `.gitignore` and `README.md` contents.

**Checked / changed:**
- Ran `python --version` and `which python` inside the venv to confirm it uses Python 3.12.16 from the project's `.venv` folder.
- Confirmed `requirements.txt` pins Pydantic **2.x** (2.14.3), not the old 1.x.
- Ran `git status` to confirm `.venv/` and cache files are ignored, so no installed libraries or secrets get committed.

**Issues caught:**
1. **Wrong assumption about Python:** the first instructions assumed `python3` would point to Python 3.12. On my Mac, `which -a python3` showed pyenv's shim runs first and points to 3.11.9. I created the venv with `python3.12` explicitly instead.
2. **Stale terminal:** `git status` failed with "Operation not permitted" because VS Code had reconnected an old terminal still sitting in the previous (trashed) project folder. Fixed by killing that terminal and opening a new one.
3. **Typo in my own .gitignore** (`".venv/` with a stray quote) meant `.venv` was still tracked (678 files showing). Caught by checking the Source Control count and `git status`; removed the quote.