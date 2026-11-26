# VendorsLink

AI-powered job platform connecting local vendors with nearby workers.

## Features
- Dual-role platform (Vendor and Worker) with registration and login
- Job posting with month-based duration and automatic expiry
- Application tracking, hiring workflow, auto-rejection of other applicants
- AI Smart Match: ranks applicants by proximity to the job location
- AI Job Match: ranks open jobs by proximity to the worker
- Business rules: no duplicate jobs, one application per job, 3-offer cap per worker

## Tech Stack
Python, Streamlit, PostgreSQL (Neon), Google Gemini API, HTML/CSS

## Run Locally
```bash
pip install -r requirements.txt
export DATABASE_URL="your_postgresql_url"
export GEMINI_API_KEY="your_gemini_key"
streamlit run vendorslink.py
```

## Live Demo
Add your Streamlit Cloud link here.
