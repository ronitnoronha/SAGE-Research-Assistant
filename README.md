# 🐼 SAGE Research Assistant - Netlify & Supabase Deployment Guide

Welcome to **SAGE Research Assistant**, an AI-powered medical vector search system configured for deployment on **Netlify** (Frontend UI) and **Supabase** (`pgvector` + Storage).

This guide walks you through every manual step required to set up Supabase, run your backend API, and deploy your frontend to Netlify.

---

## 📁 Project Structure Overview

```text
SAGE-Research-Assistant/
├── supabase/
│   └── schema.sql        # Database schema for vector storage & similarity search
├── backend/
│   ├── main.py           # FastAPI application server with CORS enabled
│   ├── rag_service.py    # Supabase Vector search & embedding logic
│   ├── requirements.txt  # Python backend dependencies
│   └── .env.example      # Environment variables template
├── frontend/
│   ├── index.html        # Modern Glassmorphism Web UI
│   ├── styles.css        # Responsive design system
│   └── app.js            # Frontend JavaScript controller
├── netlify.toml          # Netlify host deployment configuration
└── README.md             # Manual deployment step-by-step instructions
```

---

## 🛠️ Step-by-Step Deployment Instructions

### STEP 1: Set Up Supabase (Database & Vector Store)

1. **Create a Supabase Project:**
   - Go to [https://supabase.com](https://supabase.com) and log in.
   - Click **New Project**, choose a project name (e.g., `sage-medical-db`), set a database password, and choose a region.

2. **Enable Vector Extension & Create Tables:**
   - Open your project dashboard in Supabase.
   - Click on the **SQL Editor** tab in the left sidebar.
   - Click **New Query**.
   - Copy and paste the contents of `supabase/schema.sql` into the SQL editor and click **Run**.
   - *This enables `pgvector`, creates the `documents` table, and sets up the `match_documents` vector search function.*

3. **Create Storage Bucket for Research PDFs:**
   - Click on **Storage** in the left sidebar.
   - Click **New bucket**.
   - Name the bucket: `research_papers`.
   - Enable **Public bucket** (or set up bucket policy) so papers can be uploaded and viewed.

4. **Copy API Credentials:**
   - Go to **Project Settings** -> **API**.
   - Copy your **Project URL** (e.g. `https://xxxx.supabase.co`).
   - Copy your **`anon` public key** (or `service_role` key for administrative backend access).

---

### STEP 2: Deploy Backend API (Render / Railway / Cloud)

Since Netlify hosts static frontends, the Python FastAPI backend is hosted on a backend cloud provider like **Render** or **Railway** (both offer free tiers).

1. **Push your code to GitHub:**
   - Create a GitHub repository and push your project code.

2. **Deploy to Render:**
   - Go to [https://render.com](https://render.com) and log in.
   - Click **New +** -> **Web Service**.
   - Connect your GitHub repository.
   - Set **Root Directory**: `SAGE-Research-Assistant/backend`
   - Set **Build Command**: `pip install -r requirements.txt`
   - Set **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`

3. **Add Environment Variables in Render:**
   - `SUPABASE_URL`: *Your Supabase Project URL*
   - `SUPABASE_KEY`: *Your Supabase Anon / Service Role Key*
   - `GEMINI_API_KEY`: *(Optional) Your Google Gemini API Key for AI responses*

4. **Get Backend API URL:**
   - Once deployed, Render will provide a URL like `https://sage-api.onrender.com`.

---

### STEP 3: Deploy Frontend to Netlify

You can deploy the frontend to Netlify using either the **Netlify Dashboard (Drag & Drop)** or **GitHub Integration**.

#### Option A: Drag & Drop (Easiest)
1. Log into [https://netlify.com](https://netlify.com).
2. Go to **Sites** -> **Add new site** -> **Deploy manually**.
3. Drag and drop the `frontend` folder (located at `SAGE-Research-Assistant/frontend`).
4. Netlify will instantly generate a live public URL (e.g. `https://sage-assistant.netlify.app`)!

#### Option B: GitHub Integration (Continuous Deployment)
1. In Netlify Dashboard, click **Add new site** -> **Import an existing project**.
2. Select **GitHub** and authorize access to your repo.
3. Set **Base directory**: `SAGE-Research-Assistant`
4. Set **Publish directory**: `SAGE-Research-Assistant/frontend`
5. Click **Deploy Site**.

---

### STEP 4: Connect Frontend to Deployed Backend API

1. Open your live Netlify website URL in your web browser.
2. Click the ⚙️ **Settings icon** in the top right corner of the page.
3. Enter your deployed Backend API URL (e.g. `https://sage-api.onrender.com` or `http://localhost:8000` for local testing).
4. Click **Save Endpoint**.
5. Your Netlify application is now fully connected to your Supabase Vector Database!

---

## ⚡ Local Testing Instructions

To test locally before deploying to production:

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set your environment variables in `.env`:
   ```bash
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_KEY=your-supabase-key
   ```
4. Start the backend API server:
   ```bash
   python main.py
   ```
5. Open `frontend/index.html` in your browser (or serve with any static web server).
