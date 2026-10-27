"""
SuperLocal Autopilot: Project Scaffolder Module
Provides rich, production-grade starter templates for web applications, APIs,
and multi-language software projects (HTML/CSS/JS, Flask, FastAPI, React, Node, Python, Java, C, C++, SQL).
"""

import os
from pathlib import Path
from typing import Dict, Any, List


PORTFOLIO_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Portfolio | Professional Developer</title>
    <link rel="stylesheet" href="style.css">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
</head>
<body data-theme="dark">
    <!-- Navigation -->
    <header class="navbar">
        <div class="nav-container">
            <a href="#" class="logo">&lt;DevPortfolio /&gt;</a>
            <nav class="nav-links">
                <a href="#about">About</a>
                <a href="#skills">Skills</a>
                <a href="#projects">Projects</a>
                <a href="#contact">Contact</a>
                <button id="theme-toggle" class="theme-btn" aria-label="Toggle theme">☀️ Light</button>
            </nav>
        </div>
    </header>

    <!-- Hero Section -->
    <section class="hero" id="about">
        <div class="hero-content">
            <span class="badge">Full-Stack Engineer & AI Builder</span>
            <h1>Crafting resilient software with <span class="highlight">clean code</span> and modern UI.</h1>
            <p>Specializing in modern web applications, autonomous agent workflows, and cloud-native systems.</p>
            <div class="hero-actions">
                <a href="#projects" class="btn btn-primary">View Projects</a>
                <a href="#contact" class="btn btn-outline">Get In Touch</a>
            </div>
        </div>
    </section>

    <!-- Skills Section -->
    <section class="section" id="skills">
        <h2 class="section-title">Core Competencies</h2>
        <div class="skills-grid">
            <div class="skill-card">
                <h3>Frontend</h3>
                <p>HTML5, Modern CSS, Vanilla JS, React, Responsive Design, Dark Mode UI</p>
            </div>
            <div class="skill-card">
                <h3>Backend & APIs</h3>
                <p>Python, FastAPI, Flask, Node.js, RESTful Architecture, WebSockets</p>
            </div>
            <div class="skill-card">
                <h3>Automation & AI</h3>
                <p>SuperLocal Agents, Playwright, LLM Orchestration, System Scripting</p>
            </div>
            <div class="skill-card">
                <h3>DevOps & DB</h3>
                <p>Git, Docker, SQLite, PostgreSQL, CI/CD, Automated Testing</p>
            </div>
        </div>
    </section>

    <!-- Projects Section -->
    <section class="section" id="projects">
        <h2 class="section-title">Featured Projects</h2>
        <div class="projects-grid">
            <article class="project-card">
                <div class="project-header">
                    <h3>SuperLocal AI Assistant</h3>
                    <span class="tag">Python</span>
                </div>
                <p>Autonomous Windows PC assistant supporting multi-provider LLMs, desktop automation, and voice interaction.</p>
                <div class="project-footer">
                    <a href="#" class="link">Source Code →</a>
                </div>
            </article>

            <article class="project-card">
                <div class="project-header">
                    <h3>Realtime Analytics Engine</h3>
                    <span class="tag">FastAPI</span>
                </div>
                <p>High-throughput data inspection, cleaning, and chart generation dashboard.</p>
                <div class="project-footer">
                    <a href="#" class="link">View Live →</a>
                </div>
            </article>

            <article class="project-card">
                <div class="project-header">
                    <h3>Dark Mode Portfolio & Starter</h3>
                    <span class="tag">HTML / CSS / JS</span>
                </div>
                <p>Responsive, zero-dependency portfolio template with accessible dark/light theme switching and form validation.</p>
                <div class="project-footer">
                    <a href="#" class="link">Demo →</a>
                </div>
            </article>
        </div>
    </section>

    <!-- Contact Form Section -->
    <section class="section" id="contact">
        <h2 class="section-title">Contact Me</h2>
        <div class="contact-container">
            <form id="contact-form" class="contact-form">
                <div class="form-group">
                    <label for="name">Your Name</label>
                    <input type="text" id="name" name="name" required placeholder="e.g. Alex Morgan">
                </div>
                <div class="form-group">
                    <label for="email">Email Address</label>
                    <input type="email" id="email" name="email" required placeholder="alex@example.com">
                </div>
                <div class="form-group">
                    <label for="message">Message</label>
                    <textarea id="message" name="message" rows="5" required placeholder="Tell me about your project..."></textarea>
                </div>
                <button type="submit" class="btn btn-primary" id="submit-btn">Send Message</button>
                <div id="form-status" class="form-status" role="alert"></div>
            </form>
        </div>
    </section>

    <!-- Footer -->
    <footer class="footer">
        <p>&copy; 2026 Developer Portfolio. Built with SuperLocal Autopilot.</p>
    </footer>

    <script src="script.js"></script>
</body>
</html>
"""

PORTFOLIO_CSS = """:root {
    --bg-primary: #0f172a;
    --bg-surface: #1e293b;
    --bg-card: #334155;
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
    --accent: #38bdf8;
    --accent-hover: #0ea5e9;
    --border-color: #475569;
    --card-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4);
}

[data-theme="light"] {
    --bg-primary: #f8fafc;
    --bg-surface: #ffffff;
    --bg-card: #f1f5f9;
    --text-primary: #0f172a;
    --text-secondary: #475569;
    --accent: #0284c7;
    --accent-hover: #0369a1;
    --border-color: #cbd5e1;
    --card-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.08);
}

* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background-color: var(--bg-primary);
    color: var(--text-primary);
    line-height: 1.6;
    transition: background-color 0.3s ease, color 0.3s ease;
}

.navbar {
    position: sticky;
    top: 0;
    background-color: var(--bg-surface);
    border-bottom: 1px solid var(--border-color);
    z-index: 100;
}

.nav-container {
    max-width: 1100px;
    margin: 0 auto;
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem 1.5rem;
}

.logo {
    font-weight: 700;
    font-size: 1.25rem;
    color: var(--accent);
    text-decoration: none;
}

.nav-links {
    display: flex;
    align-items: center;
    gap: 1.5rem;
}

.nav-links a {
    color: var(--text-secondary);
    text-decoration: none;
    font-weight: 500;
    transition: color 0.2s;
}

.nav-links a:hover {
    color: var(--accent);
}

.theme-btn {
    background: transparent;
    border: 1px solid var(--border-color);
    color: var(--text-primary);
    padding: 0.4rem 0.8rem;
    border-radius: 6px;
    cursor: pointer;
    font-weight: 600;
}

.hero {
    max-width: 1100px;
    margin: 4rem auto;
    padding: 0 1.5rem;
}

.hero-content {
    max-width: 750px;
}

.badge {
    display: inline-block;
    padding: 0.25rem 0.75rem;
    background: rgba(56, 189, 248, 0.15);
    color: var(--accent);
    border-radius: 9999px;
    font-size: 0.875rem;
    font-weight: 600;
    margin-bottom: 1rem;
}

.hero h1 {
    font-size: 2.75rem;
    font-weight: 700;
    line-height: 1.2;
    margin-bottom: 1.25rem;
}

.highlight {
    color: var(--accent);
}

.hero p {
    font-size: 1.25rem;
    color: var(--text-secondary);
    margin-bottom: 2rem;
}

.hero-actions {
    display: flex;
    gap: 1rem;
}

.btn {
    display: inline-block;
    padding: 0.75rem 1.5rem;
    border-radius: 8px;
    font-weight: 600;
    text-decoration: none;
    cursor: pointer;
    border: none;
    transition: all 0.2s;
}

.btn-primary {
    background: var(--accent);
    color: #ffffff;
}

.btn-primary:hover {
    background: var(--accent-hover);
}

.btn-outline {
    background: transparent;
    border: 1px solid var(--border-color);
    color: var(--text-primary);
}

.btn-outline:hover {
    border-color: var(--accent);
    color: var(--accent);
}

.section {
    max-width: 1100px;
    margin: 5rem auto;
    padding: 0 1.5rem;
}

.section-title {
    font-size: 2rem;
    margin-bottom: 2.5rem;
    position: relative;
}

.section-title::after {
    content: '';
    display: block;
    width: 50px;
    height: 4px;
    background: var(--accent);
    margin-top: 0.5rem;
    border-radius: 2px;
}

.skills-grid, .projects-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 1.5rem;
}

.skill-card, .project-card {
    background: var(--bg-surface);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    padding: 1.75rem;
    box-shadow: var(--card-shadow);
    transition: transform 0.2s, border-color 0.2s;
}

.skill-card:hover, .project-card:hover {
    transform: translateY(-4px);
    border-color: var(--accent);
}

.skill-card h3 {
    margin-bottom: 0.75rem;
    color: var(--accent);
}

.skill-card p, .project-card p {
    color: var(--text-secondary);
    font-size: 0.95rem;
}

.project-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
}

.tag {
    font-size: 0.75rem;
    background: rgba(56, 189, 248, 0.1);
    color: var(--accent);
    padding: 0.2rem 0.5rem;
    border-radius: 4px;
    font-weight: 600;
}

.project-footer {
    margin-top: 1.5rem;
}

.link {
    color: var(--accent);
    text-decoration: none;
    font-weight: 600;
    font-size: 0.9rem;
}

.contact-container {
    max-width: 650px;
    background: var(--bg-surface);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    padding: 2rem;
    box-shadow: var(--card-shadow);
}

.form-group {
    margin-bottom: 1.5rem;
}

.form-group label {
    display: block;
    margin-bottom: 0.5rem;
    font-weight: 500;
}

.form-group input, .form-group textarea {
    width: 100%;
    padding: 0.75rem;
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    color: var(--text-primary);
    font-family: inherit;
    font-size: 1rem;
}

.form-group input:focus, .form-group textarea:focus {
    outline: none;
    border-color: var(--accent);
}

.form-status {
    margin-top: 1rem;
    padding: 0.75rem;
    border-radius: 6px;
    display: none;
    font-weight: 500;
}

.form-status.success {
    display: block;
    background: rgba(34, 197, 94, 0.15);
    color: #4ade80;
    border: 1px solid #22c55e;
}

.footer {
    text-align: center;
    padding: 3rem 1.5rem;
    border-top: 1px solid var(--border-color);
    color: var(--text-secondary);
    font-size: 0.9rem;
}
"""

PORTFOLIO_JS = """// SuperLocal Autopilot Portfolio Script: Dark Mode & Contact Handling
document.addEventListener('DOMContentLoaded', () => {
    const themeToggle = document.getElementById('theme-toggle');
    const body = document.body;
    const contactForm = document.getElementById('contact-form');
    const formStatus = document.getElementById('form-status');

    // 1. Theme Management
    const savedTheme = localStorage.getItem('theme') || 'dark';
    body.setAttribute('data-theme', savedTheme);
    updateToggleText(savedTheme);

    themeToggle.addEventListener('click', () => {
        const currentTheme = body.getAttribute('data-theme');
        const nextTheme = currentTheme === 'dark' ? 'light' : 'dark';
        body.setAttribute('data-theme', nextTheme);
        localStorage.setItem('theme', nextTheme);
        updateToggleText(nextTheme);
    });

    function updateToggleText(theme) {
        themeToggle.textContent = theme === 'dark' ? '☀️ Light' : '🌙 Dark';
    }

    // 2. Interactive Contact Form Submission with Validation
    if (contactForm) {
        contactForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const name = document.getElementById('name').value.trim();
            const email = document.getElementById('email').value.trim();
            const message = document.getElementById('message').value.trim();

            if (!name || !email || !message) {
                alert('Please fill out all required fields.');
                return;
            }

            formStatus.className = 'form-status success';
            formStatus.textContent = `Thank you, ${name}! Your message has been sent successfully.`;
            contactForm.reset();

            setTimeout(() => {
                formStatus.style.display = 'none';
            }, 6000);
        });
    }
});
"""

FASTAPI_MAIN_PY = """from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="SuperLocal API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Item(BaseModel):
    id: Optional[int] = None
    title: str
    completed: bool = False

ITEMS_DB: List[Item] = [
    Item(id=1, title="Explore SuperLocal Autopilot", completed=True),
    Item(id=2, title="Deploy portfolio website", completed=False),
]

@app.get("/")
def read_root():
    return {"message": "Welcome to SuperLocal FastAPI Backend", "docs": "/docs"}

@app.get("/items", response_model=List[Item])
def list_items():
    return ITEMS_DB

@app.post("/items", response_model=Item, status_code=status.HTTP_201_CREATED)
def create_item(item: Item):
    item.id = len(ITEMS_DB) + 1
    ITEMS_DB.append(item)
    return item

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
"""

FASTAPI_TEST_PY = """from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert "SuperLocal" in response.json()["message"]

def test_list_items():
    response = client.get("/items")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
"""


def scaffold_autopilot_project(
    project_type: str,
    target_dir: Path,
    project_name: str = "project",
) -> List[str]:
    """
    Scaffolds a comprehensive project workspace.
    Returns list of relative file paths created.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    created: List[str] = []

    p_type = project_type.lower().strip()

    if p_type in ("portfolio", "static_web", "html", "html_css_js", "web", "website"):
        (target_dir / "index.html").write_text(PORTFOLIO_HTML, encoding="utf-8")
        (target_dir / "style.css").write_text(PORTFOLIO_CSS, encoding="utf-8")
        (target_dir / "script.js").write_text(PORTFOLIO_JS, encoding="utf-8")
        readme = f"""# {project_name.title()}
Modern, responsive portfolio website featuring:
- Seamless Dark/Light mode toggle
- Contact form with client-side validation
- Modern CSS grid layout and clean typography

## Run Locally
Open `index.html` directly in your browser, or serve with:
```bash
python -m http.server 8080
```
Then visit: http://127.0.0.1:8080
"""
        (target_dir / "README.md").write_text(readme, encoding="utf-8")
        created.extend(["index.html", "style.css", "script.js", "README.md"])

    elif p_type in ("fastapi", "api"):
        (target_dir / "main.py").write_text(FASTAPI_MAIN_PY, encoding="utf-8")
        (target_dir / "test_main.py").write_text(FASTAPI_TEST_PY, encoding="utf-8")
        reqs = "fastapi>=0.100.0\nuvicorn>=0.23.0\npydantic>=2.0.0\npytest>=7.4.0\nhttpx>=0.24.0\n"
        (target_dir / "requirements.txt").write_text(reqs, encoding="utf-8")
        readme = f"# {project_name}\nFastAPI REST backend scaffolded by SuperLocal Autopilot.\n\n## Run\n```bash\nuvicorn main:app --reload\n```\n"
        (target_dir / "README.md").write_text(readme, encoding="utf-8")
        created.extend(["main.py", "test_main.py", "requirements.txt", "README.md"])

    elif p_type in ("flask", "flask_login"):
        # Re-use devtools Flask starter
        from tools.devtools import scaffold_project
        res = scaffold_project("flask", project_name, str(target_dir))
        created.extend(res.get("created_files", []))

    else:
        # Fallback to devtools standard scaffolder
        from tools.devtools import scaffold_project
        res = scaffold_project(p_type, project_name, str(target_dir))
        created.extend(res.get("created_files", []))

    return created
