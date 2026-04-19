const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '..', '.env') });
const express = require('express');
const cors = require('cors');
const multer = require('multer');
const fs = require('fs');
const { ApifyClient } = require('apify-client');
const admin = require('firebase-admin');

const app = express();
const PORT = process.env.PORT || 3000;
const STATIC_ROOT = __dirname;

// Middleware
app.use(cors());
app.use(express.json());
app.use(express.static(STATIC_ROOT));

// ─── Firebase Initialization ───────────────────────────────────────────
let db, bucket;
try {
  let serviceAccount;
  if (process.env.FIREBASE_SERVICE_ACCOUNT_BASE64) {
    const decoded = Buffer.from(process.env.FIREBASE_SERVICE_ACCOUNT_BASE64, 'base64').toString('utf-8');
    serviceAccount = JSON.parse(decoded);
  } else if (process.env.FIREBASE_SERVICE_ACCOUNT_JSON) {
    serviceAccount = JSON.parse(process.env.FIREBASE_SERVICE_ACCOUNT_JSON);
  } else if (fs.existsSync(path.join(__dirname, 'firebase-adminsdk.json'))) {
    serviceAccount = require('./firebase-adminsdk.json');
  }

  if (serviceAccount && process.env.FIREBASE_STORAGE_BUCKET) {
    admin.initializeApp({
      credential: admin.credential.cert(serviceAccount),
      storageBucket: process.env.FIREBASE_STORAGE_BUCKET
    });
    db = admin.firestore();
    bucket = admin.storage().bucket();
  }
} catch (error) {
  console.error('❌ Error initializing Firebase Admin SDK:', error.message);
}

// Resume storage config (Memory storage for Firebase context)
const storage = multer.memoryStorage();
const upload = multer({
  storage,
  limits: { fileSize: 5 * 1024 * 1024 }, // 5MB max
  fileFilter: (req, file, cb) => {
    if (file.mimetype === 'application/pdf') {
      cb(null, true);
    } else {
      cb(new Error('Only PDF files are allowed'));
    }
  }
});

// Gemini model configuration (same pattern as before)
const PREFERRED_GEMINI_MODEL = 'gemini-2.5-flash-lite';
const GEMINI_MODELS = [];
[
  PREFERRED_GEMINI_MODEL,
  'gemini-2.5-flash-lite-preview-09-2025',
  'gemini-2.5-pro',
].forEach(m => {
  if (m && !GEMINI_MODELS.includes(m)) GEMINI_MODELS.push(m);
});

// ─── Helper: Extract resume text from PDF ──────────────────────────────
async function getResumeText() {
  if (!bucket) return null;
  try {
    const file = bucket.file('resume.pdf');
    const [exists] = await file.exists();
    if (!exists) return null;
    
    const [buffer] = await file.download();
    const pdfParse = require('pdf-parse');
    const data = await pdfParse(buffer);
    return data.text;
  } catch (err) {
    console.error('Failed to parse resume PDF from Firebase:', err.message);
    return null;
  }
}

// ─── Helper: Call Gemini API with model fallback ───────────────────────
async function callGemini(prompt, modelIndex = 0) {
  if (modelIndex >= GEMINI_MODELS.length) {
    throw new Error('All Gemini models failed');
  }

  const model = GEMINI_MODELS[modelIndex];
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${process.env.GEMINI_API_KEY}`;

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contents: [{ parts: [{ text: prompt }] }],
        generationConfig: {
          maxOutputTokens: 4000,
          temperature: 0.7,
        }
      })
    });

    if (response.status === 429) {
      console.log(`Rate limited on ${model}, trying next...`);
      return callGemini(prompt, modelIndex + 1);
    }

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      console.log(`Gemini ${model} error: ${err.error?.message || response.statusText}`);
      return callGemini(prompt, modelIndex + 1);
    }

    const data = await response.json();
    if (!data.candidates?.[0]?.content?.parts?.[0]?.text) {
      throw new Error('Empty Gemini response');
    }

    return { text: data.candidates[0].content.parts[0].text, model };
  } catch (err) {
    if (modelIndex + 1 < GEMINI_MODELS.length) {
      return callGemini(prompt, modelIndex + 1);
    }
    throw err;
  }
}

// ─── Helper: Apify Naukri Scraper ─────────────────────────────────────
async function fetchApifyJobs(query, location = '') {
  if (!process.env.APIFY_API) return [];
  try {
    const client = new ApifyClient({ token: process.env.APIFY_API });

    // Build keyword combining query + location so the actor searches correctly
    const keyword = location ? `${query} ${location}` : query;

    const run = await client.actor('codemaverick/naukri-job-scraper-latest').call({
      keyword,
      location: location || 'India',
      maxItems: 50,
    });

    // listItems() is the correct method in apify-client v9+ (iterateItems does not exist)
    const datasetResult = await client.dataset(run.defaultDatasetId).listItems({ limit: 100 });
    const items = datasetResult.items || [];
    console.log(`[Apify] Naukri returned ${items.length} items from dataset ${run.defaultDatasetId}`);

    // Normalise Naukri items to the same shape as JSearch jobs
    // Naukri actor output uses capitalized spaced keys: "Job Title", "Company", "Job URL", etc.
    return items.map((item, i) => ({
      id: `apify_${item['Job ID'] || i}_${Date.now()}`,
      title: item['Job Title'] || item.title || item.jobTitle || 'Unknown Role',
      company: item['Company'] || item.company || item.companyName || 'Unknown Company',
      logo: item.logo || item.companyLogo || null,
      location: item['Location'] || item.location || item.jobLocation || location || 'India',
      employment_type: item['Employment Type'] || item.jobType || 'Full-time',
      is_remote: (item['Location'] || item.location || '').toLowerCase().includes('remote') ||
                 (item['Job Title'] || item.title || '').toLowerCase().includes('remote'),
      posted: item['Posted Time'] || item.postedOn || item.postedDate || '',
      posted_utc: '',
      apply_link: item['Job URL'] || item.applyLink || item.jobLink || item.url || '',
      apply_options: [],
      description: item['Description'] || item.description || item.jobDescription || '',
      description_short: (item['Description'] || item.description || '').substring(0, 300) + '...',
      salary: item['Salary'] || item.salary || item.salaryRange || null,
      experience: item['Experience Required'] || null,
      skills: item['Skills/Tags'] || null,
      benefits: [],
      publisher: 'Naukri (Apify)',
      google_link: '',
      source: 'apify',
    }));
  } catch (err) {
    console.error('[Apify] Naukri scraper error:', err.message);
    return [];
  }
}

// ═══════════════════════════════════════════════════════════════════════
// API ROUTES
// ═══════════════════════════════════════════════════════════════════════

// ─── Job Search (RapidAPI JSearch) ─────────────────────────────────────
app.get('/api/search', async (req, res) => {
  const { q, location, page = 1, date_posted = 'all', remote_only = false, employment_type } = req.query;

  if (!q) return res.status(400).json({ error: 'Query parameter "q" is required' });

  const query = location ? `${q} in ${location}` : q;
  const params = new URLSearchParams({
    query,
    page: String(page),
    num_pages: '1',
    country: 'in',
    date_posted,
  });
  if (remote_only === 'true') params.set('remote_jobs_only', 'true');
  if (employment_type) params.set('employment_types', employment_type);

  try {
    const response = await fetch(`https://jsearch.p.rapidapi.com/search?${params}`, {
      headers: {
        'Content-Type': 'application/json',
        'x-rapidapi-host': 'jsearch.p.rapidapi.com',
        'x-rapidapi-key': process.env.RAPIDAPI_KEY,
      }
    });

    if (!response.ok) {
      const errText = await response.text();
      console.error('JSearch error:', response.status, errText);
      return res.status(response.status).json({ error: 'Job search failed', detail: errText });
    }

    const data = await response.json();
    // Normalize to a cleaner format for the frontend
    const jobs = (data.data || []).map((job, i) => ({
      id: job.job_id || `job_${i}`,
      title: job.job_title,
      company: job.employer_name,
      logo: job.employer_logo,
      location: job.job_city
        ? `${job.job_city}${job.job_state ? ', ' + job.job_state : ''}`
        : job.job_location || 'India',
      employment_type: job.job_employment_type || 'Full-time',
      is_remote: job.job_is_remote || false,
      posted: job.job_posted_at || '',
      posted_utc: job.job_posted_at_datetime_utc || '',
      apply_link: job.job_apply_link || '',
      apply_options: (job.apply_options || []).map(opt => ({
        link: opt.apply_link,
        publisher: opt.publisher,
        is_direct: opt.is_direct,
      })),
      description: job.job_description || '',
      description_short: (job.job_description || '').substring(0, 300) + '...',
      salary: job.job_min_salary && job.job_max_salary
        ? `${job.job_min_salary}–${job.job_max_salary} ${job.job_salary_currency || ''}`
        : null,
      benefits: job.job_benefits_strings || [],
      publisher: job.job_publisher || '',
      google_link: job.job_google_link || '',
    }));

    res.json({ status: 'OK', count: jobs.length, jobs, source: 'rapidapi' });
  } catch (err) {
    console.error('Search error:', err);
    res.status(500).json({ error: 'Internal search error', message: err.message });
  }
});

// ─── Job Search (Apify Naukri) ──────────────────────────────────────────
app.get('/api/search/apify', async (req, res) => {
  const { q, location } = req.query;
  if (!q) return res.status(400).json({ error: 'Query parameter "q" is required' });

  const jobs = await fetchApifyJobs(q, location || 'India');
  res.json({ status: 'OK', count: jobs.length, jobs, source: 'apify' });
});

// ─── Merged Search: RapidAPI + Apify → Gemini Rank ─────────────────────
app.get('/api/search/merged', async (req, res) => {
  const { q, location, page = 1, date_posted = 'all', remote_only = false, employment_type } = req.query;
  if (!q) return res.status(400).json({ error: 'Query parameter "q" is required' });

  const loc = location || 'India';
  const query = location ? `${q} in ${location}` : q;
  const params = new URLSearchParams({ query, page: String(page), num_pages: '1', country: 'in', date_posted });
  if (remote_only === 'true') params.set('remote_jobs_only', 'true');
  if (employment_type) params.set('employment_types', employment_type);

  // ── Fetch both sources in parallel ──
  const [rapidResult, apifyJobs] = await Promise.allSettled([
    // JSearch (RapidAPI)
    fetch(`https://jsearch.p.rapidapi.com/search?${params}`, {
      headers: {
        'Content-Type': 'application/json',
        'x-rapidapi-host': 'jsearch.p.rapidapi.com',
        'x-rapidapi-key': process.env.RAPIDAPI_KEY,
      }
    }).then(r => r.json()),
    // Apify Naukri
    fetchApifyJobs(q, loc),
  ]);

  // ── Normalise RapidAPI results ──
  let rapidJobs = [];
  if (rapidResult.status === 'fulfilled' && rapidResult.value?.data) {
    rapidJobs = rapidResult.value.data.map((job, i) => ({
      id: job.job_id || `rapid_${i}`,
      title: job.job_title,
      company: job.employer_name,
      logo: job.employer_logo,
      location: job.job_city ? `${job.job_city}${job.job_state ? ', ' + job.job_state : ''}` : job.job_location || 'India',
      employment_type: job.job_employment_type || 'Full-time',
      is_remote: job.job_is_remote || false,
      posted: job.job_posted_at || '',
      posted_utc: job.job_posted_at_datetime_utc || '',
      apply_link: job.job_apply_link || '',
      apply_options: (job.apply_options || []).map(o => ({ link: o.apply_link, publisher: o.publisher, is_direct: o.is_direct })),
      description: job.job_description || '',
      description_short: (job.job_description || '').substring(0, 300) + '...',
      salary: job.job_min_salary && job.job_max_salary ? `${job.job_min_salary}–${job.job_max_salary} ${job.job_salary_currency || ''}` : null,
      benefits: job.job_benefits_strings || [],
      publisher: job.job_publisher || 'JSearch',
      google_link: job.job_google_link || '',
      source: 'rapidapi',
    }));
  } else if (rapidResult.status === 'rejected') {
    console.error('[RapidAPI] error:', rapidResult.reason?.message);
  }

  const apifyJobsList = apifyResult => apifyJobs.status === 'fulfilled' ? apifyJobs.value : [];
  const allApify = apifyJobs.status === 'fulfilled' ? apifyJobs.value : [];

  // ── Deduplicate by title+company (case-insensitive) ──
  const seen = new Set();
  const merged = [];
  for (const job of [...rapidJobs, ...allApify]) {
    const key = `${job.title?.toLowerCase().trim()}|${job.company?.toLowerCase().trim()}`;
    if (!seen.has(key)) {
      seen.add(key);
      merged.push(job);
    }
  }

  res.json({
    status: 'OK',
    count: merged.length,
    rapid_count: rapidJobs.length,
    apify_count: allApify.length,
    jobs: merged,
    source: 'merged',
  });
});

// ─── AI: Rank & Match Jobs ─────────────────────────────────────────────
app.post('/api/ai/rank', async (req, res) => {
  const { jobs } = req.body;
  if (!jobs || !jobs.length) return res.status(400).json({ error: 'No jobs to rank' });

  const resumeText = await getResumeText();

  const prompt = `You are a job matching AI. Analyze these job listings against the candidate profile and return a ranked list.

CANDIDATE PROFILE:
- Name: Surya
- Role: Software Developer & Linux Admin at Infosys, Hyderabad
- Skills: Linux, Git, Docker, Python, microservices, REST APIs, Docker Compose, RabbitMQ, JWT/auth, SQL/NoSQL, CI/CD, cloud storage, Ollama/Mistral
- Experience: ~3+ years
- Preferred locations: Bengaluru, Hyderabad
- Min package: 7–8 LPA INR
- Target roles: DevOps, SRE, Backend Dev, Platform Engineer, Linux Admin, Cloud Engineer
${resumeText ? '\nRESUME TEXT:\n' + resumeText.substring(0, 2000) : ''}

JOB LISTINGS:
${jobs.map((j, i) => `[${i}] "${j.title}" at "${j.company}" in ${j.location}\nDescription: ${(j.description || '').substring(0, 500)}`).join('\n\n')}

For each job, respond with ONLY valid JSON (no markdown fences):
{
  "rankings": [
    {
      "index": 0,
      "match_score": 85,
      "matched_skills": ["Linux", "Docker", "Git"],
      "missing_skills": ["Terraform"],
      "reason": "Strong match — requires core Linux and Docker skills..."
    }
  ]
}`;

  try {
    const { text, model } = await callGemini(prompt);
    const clean = text.replace(/```json|```/g, '').trim();
    const parsed = JSON.parse(clean);
    res.json({ ...parsed, model });
  } catch (err) {
    console.error('AI rank error:', err);
    res.status(500).json({ error: 'AI ranking failed', message: err.message });
  }
});

// ─── AI: Cover Letter ──────────────────────────────────────────────────
app.post('/api/ai/cover-letter', async (req, res) => {
  const { jobTitle, company, location, description, skills } = req.body;
  if (!jobTitle || !company) return res.status(400).json({ error: 'Job title and company are required' });

  const resumeText = await getResumeText();

  const prompt = `Write a concise, professional, and confident cover letter for Surya applying for the role of "${jobTitle}" at "${company}" in ${location || 'India'}.

CANDIDATE:
- Software Developer & Linux Admin at Infosys, Hyderabad
- Skills: Linux, Git, Docker, Python, microservices, REST APIs, Docker Compose, RabbitMQ, JWT/auth, SQL/NoSQL, CI/CD
- Experience: ~2+ years
- Contact: illasuryanani2001@gmail.com | +91 9346358559
- LinkedIn: https://www.linkedin.com/in/surya-teja-illa-706108232/
- GitHub: https://github.com/Suryatejaa
${resumeText ? '\nRESUME SUMMARY:\n' + resumeText.substring(0, 1500) : ''}

JOB DESCRIPTION (excerpt):
${(description || '').substring(0, 1500)}

${skills ? 'Required skills: ' + (Array.isArray(skills) ? skills.join(', ') : skills) : ''}

Write 3-4 short paragraphs. Confident tone, no generic fluff. Mention specific skills that match. End with enthusiasm. Do NOT wrap in code fences.`;

  try {
    const { text, model } = await callGemini(prompt);
    const clean = text.replace(/^```[\w]*\n|\n```$/g, '').trim();
    res.json({ coverLetter: clean, model });
  } catch (err) {
    console.error('Cover letter error:', err);
    res.status(500).json({ error: 'Cover letter generation failed', message: err.message });
  }
});

// ─── Resume Upload ─────────────────────────────────────────────────────
app.post('/api/resume/upload', upload.single('resume'), async (req, res) => {
  if (!req.file) return res.status(400).json({ error: 'No file uploaded' });
  if (!bucket) return res.status(500).json({ error: 'Firebase bucket not configured. Check env variables.' });

  try {
    const file = bucket.file('resume.pdf');
    await file.save(req.file.buffer, {
      metadata: { contentType: req.file.mimetype }
    });
    
    res.json({
      success: true,
      filename: req.file.originalname,
      size: req.file.size,
    });
  } catch (err) {
    console.error('Upload error:', err);
    res.status(500).json({ error: 'Upload failed', message: err.message });
  }
});

app.get('/api/resume/status', async (req, res) => {
  if (!bucket) return res.json({ uploaded: false });
  try {
    const file = bucket.file('resume.pdf');
    const [exists] = await file.exists();
    if (exists) {
      const [metadata] = await file.getMetadata();
      res.json({
        uploaded: true,
        size: metadata.size,
        modified: metadata.updated,
      });
    } else {
      res.json({ uploaded: false });
    }
  } catch (err) {
    res.json({ uploaded: false });
  }
});

app.get('/api/resume/download', async (req, res) => {
  if (!bucket) return res.status(404).json({ error: 'Firebase not configured' });
  try {
    const file = bucket.file('resume.pdf');
    const [exists] = await file.exists();
    if (exists) {
      res.setHeader('Content-Type', 'application/pdf');
      res.setHeader('Content-Disposition', 'attachment; filename="Surya_Resume.pdf"');
      file.createReadStream().pipe(res);
    } else {
      res.status(404).json({ error: 'No resume found' });
    }
  } catch (err) {
    res.status(500).json({ error: 'Download failed', message: err.message });
  }
});

// ─── Application Tracking ──────────────────────────────────────────────
app.get('/api/applications', async (req, res) => {
  if (!db) return res.json([]);
  try {
    const snapshot = await db.collection('applications').orderBy('appliedAt', 'asc').get();
    const apps = snapshot.docs.map(doc => doc.data());
    res.json(apps);
  } catch (err) {
    console.error('Error fetching applications:', err);
    res.json([]);
  }
});

app.post('/api/applications', async (req, res) => {
  const { jobId, title, company, location, apply_link, coverLetter } = req.body;
  if (!jobId || !title) return res.status(400).json({ error: 'Missing job data' });
  if (!db) return res.status(500).json({ error: 'Firebase not configured' });

  try {
    const docRef = db.collection('applications').doc(jobId);
    const doc = await docRef.get();
    if (doc.exists) {
      return res.status(409).json({ error: 'Already applied to this job' });
    }
    
    const appData = {
      jobId,
      title,
      company,
      location,
      apply_link,
      coverLetter: coverLetter || null,
      appliedAt: new Date().toISOString(),
      status: 'applied',
    };
    
    await docRef.set(appData);
    
    // Get total count
    const snapshot = await db.collection('applications').count().get();
    const total = snapshot.data().count;
    
    res.json({ success: true, application: appData, total });
  } catch (err) {
    res.status(500).json({ error: 'Failed to save application', message: err.message });
  }
});

app.delete('/api/applications/:jobId', async (req, res) => {
  if (!db) return res.status(500).json({ error: 'Firebase not configured' });
  try {
    await db.collection('applications').doc(req.params.jobId).delete();
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: 'Failed to delete', message: err.message });
  }
});

// ─── Serve frontend ────────────────────────────────────────────────────
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'index.html'));
});

// ─── Start ─────────────────────────────────────────────────────────────
app.listen(PORT, () => {
  console.log(`\n  🚀 Job Hunter Agent running at http://localhost:${PORT}\n`);
  console.log(`  API Keys & Services loaded:`);
  console.log(`    • Gemini:   ${process.env.GEMINI_API_KEY ? '✓' : '✗ MISSING'}`);
  console.log(`    • RapidAPI: ${process.env.RAPIDAPI_KEY ? '✓' : '✗ MISSING'}`);
  console.log(`    • Apify:    ${process.env.APIFY_API ? '✓' : '✗ MISSING'}`);
  console.log(`    • Firebase: ${db && bucket ? '✓ Connected' : '✗ MISSING or FAILED'}`);
  console.log(`  Gemini models: ${GEMINI_MODELS.join(' → ')}\n`);
});
