# How to Run the Incident Management System (with AI)

## 1. Database migration (for AI and extra fields)

Run the migration so the app can store error/logs, impact, and AI analysis:

```bash
# Connect to your MySQL (incident_db) and run:
mysql -h <host> -P 4040 -u <user> -p incident_db < migrations/add_ai_analysis_columns.sql
```

Or run the `ALTER TABLE` statements from `migrations/add_ai_analysis_columns.sql` in your MySQL client.  
If you skip this, the app still works: new incidents use only service, severity, description, and no AI analysis is stored.

## 2. Gemini API key (for AI analysis)

**Why free tiers often “don’t work”:**
- **Groq:** Free but **blocks many regions** (403). If you’re not in US/EU etc., you get 403 even with a valid key.
- **Gemini/OpenAI:** Free tier has **quota limits**; once exceeded you see “quota” or “billing” until it resets or you add a new project/key.

**Use Hugging Face (free, works globally, no region block):**

- **No credit card.** ~300 requests/hour. Works in **all regions**.
- Get a token at **[https://huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)** (sign up, then “Create new token” with **Read** access).

- **Windows (PowerShell):**
  ```powershell
  $env:GEMINI_API_KEY = "your-gemini-api-key"
  python app.py
  ```

- **Linux / macOS:**
  ```bash
  export GEMINI_API_KEY=your-gemini-api-key
  python app.py
  ```

If GEMINI_API_KEY is not set  if that’s not set,  If GEMINI_API_KEY is not set, incidents are still created but AI analysis will not be generated.

**Optional – Groq (free but region-restricted):** If you’re in a supported region, you can set `GEMINI_API_KEY` instead of or in addition to `HF_TOKEN`. 
## 3. Install dependencies

```bash
cd incidents-management-main
pip install -r requirements.txt
```

## 4. Run the app

**Development (Flask):**
```bash
python app.py
```
Then open: **http://localhost:5000**

**Production (Gunicorn):**
```bash
gunicorn -b 0.0.0.0:5000 app:app
```

**With Docker:**
```bash
docker build -t incidents-app .
docker run -p 5000:5000 -e GEMINI_API_KEY=your-gemini-key incidents-app
```

**With Docker Compose:**  
Set `GEMINI_API_KEY` in the environment for the service (e.g. in `docker-compose.yml` or a `.env` file), then:
```bash
docker-compose up -d
```

## 5. What the AI integration does

- When you **create an incident** (service, severity, description, and optionally error/logs and impact), the app sends these details to **Google Gemini**.
- Gemini returns a **structured analysis**: summary, possible root causes, troubleshooting steps, suggested fixes, and preventive measures.
- That text is **saved** on the incident and **shown** on the incident’s **Manage** (edit) page under “AI Analysis & Recommendations”.

So: create incident → AI runs automatically → open the incident to see the analysis.
