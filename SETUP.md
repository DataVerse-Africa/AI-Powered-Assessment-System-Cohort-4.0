# Patient Assessment System — Setup Guide
## VSCode Environment Setup (Do This First)

---

### Step 0 — Prerequisites
Make sure you have these installed on your machine before anything else:
- **Python 3.11** — https://www.python.org/downloads/
- **VSCode** — https://code.visualstudio.com/
- **VSCode Python Extension** — search "Python" by Microsoft in the Extensions panel

---

### Step 1 — Open the Project in VSCode

1. Unzip the downloaded `patient_assessment_api.zip`
2. Open VSCode
3. Go to **File → Open Folder** and select the `patient_assessment_api` folder
4. You should see the full folder structure in the left sidebar

---

### Step 2 — Create a Virtual Environment

Open the VSCode **integrated terminal**:
- **Windows**: `` Ctrl + ` ``
- **Mac**: `` Cmd + ` ``

Then run:

```bash
# Make sure you are inside the patient_assessment_api folder
# You should see something like:  C:\Users\you\patient_assessment_api>

# Create the virtual environment (named 'venv')
python -m venv venv
```

---

### Step 3 — Activate the Virtual Environment

**Windows (Command Prompt or PowerShell):**
```bash
venv\Scripts\activate
```

**Mac / Linux:**
```bash
source venv/bin/activate
```

After activation you will see `(venv)` at the start of your terminal line.
That confirms you are inside the isolated environment.

> ⚠️ You must activate the virtual environment EVERY TIME you open a new terminal session.
> VSCode can do this automatically — see Step 5.

---

### Step 4 — Install All Dependencies

With the virtual environment active, run:

```bash
pip install -r requirements.txt
```

This installs every library the project needs. It may take 2–5 minutes the first time
because TensorFlow is included.

To verify the key packages installed correctly:
```bash
python -c "import fastapi; print('FastAPI OK:', fastapi.__version__)"
python -c "import sqlalchemy; print('SQLAlchemy OK:', sqlalchemy.__version__)"
python -c "import tensorflow; print('TensorFlow OK:', tensorflow.__version__)"
```

---

### Step 5 — Select the Virtual Environment in VSCode

1. Press **Ctrl+Shift+P** (Windows) or **Cmd+Shift+P** (Mac) to open the command palette
2. Type: `Python: Select Interpreter`
3. Choose the interpreter that shows `venv` in the path
   - Windows: something like `.\venv\Scripts\python.exe`
   - Mac/Linux: something like `./venv/bin/python`

VSCode will now automatically activate `venv` every time you open a new terminal in this project.

---

### Step 6 — Create Your .env File

In the project root, duplicate the `.env.example` file and rename the copy to `.env`:

```bash
# Windows
copy .env.example .env

# Mac / Linux
cp .env.example .env
```

Open `.env` and fill in your values:
- Change `SECRET_KEY` to a long random string
- Change `ADMIN_EMAIL` to your preferred admin email
- Change `ADMIN_PASSWORD` to a strong admin password
- Change `ADMIN_SECRET_KEY` to a different long random string

To generate secure random keys, run:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
Run that twice — use one value for `SECRET_KEY` and another for `ADMIN_SECRET_KEY`.

> ⚠️ The `.env` file is already in `.gitignore`. Never commit it to git.

---

### Step 7 — Verify the Project Structure

Your folder should look like this:

```
patient_assessment_api/
├── main.py
├── .env                  ← you created this in Step 6
├── .env.example
├── .gitignore
├── requirements.txt
├── SETUP.md
│
├── database/
│   ├── __init__.py
│   ├── models.py
│   └── session.py
│
├── auth/
│   ├── __init__.py
│   ├── security.py
│   ├── dependencies.py
│   └── router.py
│
├── routers/
│   ├── __init__.py
│   ├── sessions.py
│   ├── predictions.py
│   ├── user_panel.py
│   └── admin_panel.py
│
├── schemas/
│   ├── __init__.py
│   ├── auth_schemas.py
│   ├── session_schemas.py
│   ├── prediction_schemas.py
│   └── user_schemas.py
│
├── ml_models/
│   ├── __init__.py
│   ├── diabetes_inference.py
│   ├── cardiovascular_inference.py
│   ├── ckd_inference.py
│   └── kidney_cnn_inference.py
│
└── saved_models/
    └── README.txt        ← place your .pkl and .keras files here
```

---

### Step 8 — Recommended VSCode Extensions

Install these from the Extensions panel (Ctrl+Shift+X):

| Extension | Publisher | Why |
|---|---|---|
| Python | Microsoft | Core Python support, linting, IntelliSense |
| Pylance | Microsoft | Fast type checking and autocomplete |
| Thunder Client | Rangav | Test API endpoints directly inside VSCode (alternative to Postman) |
| SQLite Viewer | Florian Klampfer | View your SQLite database file visually |
| Python Indent | Kevin Rose | Fixes Python indentation behaviour in VSCode |
| GitLens | GitKraken | Better git history and blame annotations |

---

### Build Order (Step by Step with Your Instructor)

| Step | What We Build | Files Touched |
|---|---|---|
| Step 1 | Database models + connection | `database/models.py`, `database/session.py` | ✅
| Step 2 | Authentication (register, login, admin login) | `auth/security.py`, `auth/dependencies.py`, `auth/router.py`, `schemas/auth_schemas.py` | ✅
| Step 3 | Clinical sessions (create, list, close, delete) | `routers/sessions.py`, `schemas/session_schemas.py` | ✅
| Step 4 | ML prediction endpoints | `routers/predictions.py`, `schemas/prediction_schemas.py`, `ml_models/*.py` | ✅
| Step 5 | Patient user panel | `routers/user_panel.py`, `schemas/user_schemas.py` | ✅
| Step 6 | Admin panel + CSV export | `routers/admin_panel.py` | ✅
| Final | Wire everything together | `main.py` | ✅

integrating the AI-Powered assistance aspect

Build order:
- create your groq account to get your API key
`database/models.py` — add the ChatMessage table
`schemas/chat_schemas.py` — request and response schemas
`routers/chat.py` — the three chatbot endpoints
`main.py` — register the chat router

---

### Running the Server (After All Steps Are Complete)

```bash
uvicorn main:app --reload --port 8000
```

Then open your browser at:
- **API docs (interactive):** http://localhost:8000/docs
- **Health check:** http://localhost:8000/api/health
