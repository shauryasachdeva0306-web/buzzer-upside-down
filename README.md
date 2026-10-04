# Quiz Buzzer (Python) – run and deploy

Teams open the site, type a team name and tap the buzzer.
You open /host, enter your PIN, and control everything.
Needs Python 3.8+ and nothing else (no pip packages).

## Run on your laptop
    HOST_PIN=4821 python server.py          (Windows: set HOST_PIN=4821, then python server.py)
Host page: http://localhost:3000/host   Teams: the address printed in the terminal (same Wi-Fi).

## Deploy on Render
1. Put this folder in a GitHub repository.
2. render.com > New > Blueprint > choose the repo (it reads render.yaml).
3. Enter your HOST_PIN when asked.
4. Open https://YOUR-APP.onrender.com/host. The QR code there is what teams scan.

## Deploy on Railway
1. New Project > Deploy from GitHub repo (the Procfile starts the app).
2. Variables: HOST_PIN=your-pin, APP_ENV=production
3. Generate a domain, then add PUBLIC_URL=https://your-domain

## Deploy with Docker (any server)
    docker build -t quiz-buzzer .
    docker run -d -p 80:3000 -e HOST_PIN=your-pin -e PUBLIC_URL=http://your-server-ip/ --restart unless-stopped quiz-buzzer

## Important
- Run exactly ONE copy. Presses and scores live in memory; a restart clears them.
- Use an always-on plan, not a sleeping free one. Use https.
- This needs a host that lets a Python program stay running (Render, Railway,
  Docker, a VPS). Hosts that only run short web requests, such as the free
  PythonAnywhere plan, will not work.
- Variables: HOST_PIN (required), PORT (set by the host), PUBLIC_URL (optional, for the QR code).
