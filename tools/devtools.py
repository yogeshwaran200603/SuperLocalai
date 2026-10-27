"""
Astra-Local Developer Tools
Project scaffolding (Flask, React, Python, Java, C, C++, SQL),
automated testing, and self-healing test fix runners.
"""

import os
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from config import WORKSPACE_DIR


FLASK_LOGIN_APP_PY = """from flask import Flask, render_template, request, redirect, url_for, session, flash
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# In-memory users for demonstration
USERS = {
    "admin": "password123",
    "user": "welcome123"
}

@app.route("/")
def index():
    if "user" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        if username in USERS and USERS[username] == password:
            session["user"] = username
            flash("Login successful!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid username or password.", "danger")
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template("dashboard.html", user=session["user"])

@app.route("/logout")
def logout():
    session.pop("user", None)
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))

if __name__ == "__main__":
    print("Starting Flask app on http://127.0.0.1:5000 ...")
    app.run(debug=True, port=5000)
"""

FLASK_LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Login - Flask App</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
    <div class="auth-container">
        <h2>Welcome Back</h2>
        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for category, msg in messages %}
              <div class="alert alert-{{ category }}">{{ msg }}</div>
            {% endfor %}
          {% endif %}
        {% endwith %}
        <form method="POST">
            <div class="form-group">
                <label>Username</label>
                <input type="text" name="username" placeholder="e.g. admin" required>
            </div>
            <div class="form-group">
                <label>Password</label>
                <input type="password" name="password" placeholder="e.g. password123" required>
            </div>
            <button type="submit" class="btn">Sign In</button>
        </form>
        <p class="demo-hint">Demo accounts: <code>admin</code> / <code>password123</code></p>
    </div>
</body>
</html>
"""

FLASK_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Dashboard</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
    <div class="auth-container">
        <h2>Dashboard</h2>
        <p>Welcome, <strong>{{ user }}</strong>! You are securely logged in.</p>
        <a href="{{ url_for('logout') }}" class="btn btn-secondary">Log Out</a>
    </div>
</body>
</html>
"""

FLASK_STYLE_CSS = """body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: #f0f2f5;
    display: flex;
    justify-content: center;
    align-items: center;
    height: 100vh;
    margin: 0;
}
.auth-container {
    background: white;
    padding: 30px;
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    width: 320px;
}
h2 { margin-top: 0; color: #1a1a1a; text-align: center; }
.form-group { margin-bottom: 15px; }
label { display: block; margin-bottom: 5px; font-size: 14px; color: #555; }
input { width: 100%; padding: 10px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }
.btn { width: 100%; padding: 10px; background: #0066cc; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; margin-top: 10px; text-decoration: none; display: inline-block; text-align: center; }
.btn-secondary { background: #6c757d; }
.alert { padding: 10px; border-radius: 4px; margin-bottom: 15px; font-size: 14px; }
.alert-danger { background: #f8d7da; color: #721c24; }
.alert-success { background: #d4edda; color: #155724; }
.alert-info { background: #d1ecf1; color: #0c5460; }
.demo-hint { font-size: 12px; color: #888; text-align: center; margin-top: 15px; }
"""


def scaffold_project(template: str, project_name: str, target_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Scaffolds a project from templates:
    - flask: Complete Flask web app with login, session management, dashboard, templates, and styles.
    - react: Vite React app boilerplate.
    - python: Modern Python package with tests.
    - java, c, cpp, sql: Base boilerplate structures.
    """
    try:
        base = Path(os.path.expandvars(target_dir)).resolve() if target_dir else WORKSPACE_DIR
        proj_dir = base / project_name
        proj_dir.mkdir(parents=True, exist_ok=True)

        template = template.lower().strip()
        created_files = []

        if template == "flask":
            # 1. app.py
            app_py = proj_dir / "app.py"
            app_py.write_text(FLASK_LOGIN_APP_PY, encoding="utf-8")
            created_files.append("app.py")

            # 2. templates/
            tpl_dir = proj_dir / "templates"
            tpl_dir.mkdir(exist_ok=True)
            (tpl_dir / "login.html").write_text(FLASK_LOGIN_HTML, encoding="utf-8")
            (tpl_dir / "dashboard.html").write_text(FLASK_DASHBOARD_HTML, encoding="utf-8")
            created_files.extend(["templates/login.html", "templates/dashboard.html"])

            # 3. static/
            static_dir = proj_dir / "static"
            static_dir.mkdir(exist_ok=True)
            (static_dir / "style.css").write_text(FLASK_STYLE_CSS, encoding="utf-8")
            created_files.append("static/style.css")

            # 4. requirements.txt
            (proj_dir / "requirements.txt").write_text("flask>=3.0.0\n", encoding="utf-8")
            created_files.append("requirements.txt")

            # 5. README.md
            readme = f"# {project_name}\n\nFlask application with authentication.\n\n## Run\n```bash\npip install -r requirements.txt\npython app.py\n```\n"
            (proj_dir / "README.md").write_text(readme, encoding="utf-8")
            created_files.append("README.md")

        elif template == "python":
            src_dir = proj_dir / "src"
            src_dir.mkdir(exist_ok=True)
            (src_dir / "__init__.py").write_text('__version__ = "0.1.0"\n', encoding="utf-8")
            (src_dir / "main.py").write_text('def main():\n    print("Hello from ' + project_name + '!")\n\nif __name__ == "__main__":\n    main()\n', encoding="utf-8")

            test_dir = proj_dir / "tests"
            test_dir.mkdir(exist_ok=True)
            (test_dir / "test_main.py").write_text("def test_sample():\n    assert True\n", encoding="utf-8")

            (proj_dir / "requirements.txt").write_text("pytest>=7.0.0\n", encoding="utf-8")
            created_files.extend(["src/__init__.py", "src/main.py", "tests/test_main.py", "requirements.txt"])

        elif template == "react":
            package_json = '{\n  "name": "' + project_name + '",\n  "private": true,\n  "version": "0.1.0",\n  "type": "module",\n  "scripts": {\n    "dev": "vite",\n    "build": "vite build",\n    "preview": "vite preview"\n  },\n  "dependencies": {\n    "react": "^18.3.1",\n    "react-dom": "^18.3.1"\n  },\n  "devDependencies": {\n    "@vitejs/plugin-react": "^4.3.1",\n    "vite": "^5.4.0"\n  }\n}\n'
            (proj_dir / "package.json").write_text(package_json, encoding="utf-8")
            (proj_dir / "vite.config.js").write_text('import { defineConfig } from "vite";\nimport react from "@vitejs/plugin-react";\n\nexport default defineConfig({\n  plugins: [react()],\n});\n', encoding="utf-8")
            (proj_dir / "index.html").write_text('<!DOCTYPE html>\n<html lang="en">\n<head>\n  <meta charset="UTF-8">\n  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n  <title>' + project_name + '</title>\n</head>\n<body>\n  <div id="root"></div>\n  <script type="module" src="/src/main.jsx"></script>\n</body>\n</html>\n', encoding="utf-8")
            
            src_dir = proj_dir / "src"
            src_dir.mkdir(exist_ok=True)
            (src_dir / "main.jsx").write_text('import React from "react";\nimport ReactDOM from "react-dom/client";\nimport App from "./App.jsx";\nimport "./index.css";\n\nReactDOM.createRoot(document.getElementById("root")).render(\n  <React.StrictMode>\n    <App />\n  </React.StrictMode>\n);\n', encoding="utf-8")
            (src_dir / "App.jsx").write_text('export default function App() {\n  return (\n    <div className="container">\n      <h1>Welcome to ' + project_name + '</h1>\n      <p>A modern React + Vite application.</p>\n    </div>\n  );\n}\n', encoding="utf-8")
            (src_dir / "index.css").write_text('body { font-family: system-ui, sans-serif; margin: 0; padding: 2rem; background: #121212; color: #fff; text-align: center; }\n.container { max-width: 600px; margin: 0 auto; }\n', encoding="utf-8")
            (proj_dir / "README.md").write_text(f"# {project_name}\n\nReact application built with Vite.\n\n## Quick Start\n```bash\nnpm install\nnpm run dev\n```\n", encoding="utf-8")
            created_files.extend(["package.json", "vite.config.js", "index.html", "src/main.jsx", "src/App.jsx", "src/index.css", "README.md"])

        elif template == "java":
            pom_xml = f"""<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.app</groupId>
    <artifactId>{project_name}</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.source>17</maven.compiler.source>
        <maven.compiler.target>17</maven.compiler.target>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter-api</artifactId>
            <version>5.10.0</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
"""
            (proj_dir / "pom.xml").write_text(pom_xml, encoding="utf-8")

            java_src_dir = proj_dir / "src" / "main" / "java" / "com" / "app"
            java_src_dir.mkdir(parents=True, exist_ok=True)
            app_java = """package com.app;

public class App {
    public static String getGreeting() {
        return "Hello from Java App!";
    }

    public static void main(String[] args) {
        System.out.println(getGreeting());
    }
}
"""
            (java_src_dir / "App.java").write_text(app_java, encoding="utf-8")

            java_test_dir = proj_dir / "src" / "test" / "java" / "com" / "app"
            java_test_dir.mkdir(parents=True, exist_ok=True)
            app_test_java = """package com.app;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

public class AppTest {
    @Test
    public void testGreeting() {
        assertNotNull(App.getGreeting());
        assertTrue(App.getGreeting().contains("Hello"));
    }
}
"""
            (java_test_dir / "AppTest.java").write_text(app_test_java, encoding="utf-8")
            (proj_dir / "README.md").write_text(f"# {project_name}\n\nStandard Java Maven application.\n\n## Build & Test\n```bash\nmvn clean test\nmvn compile exec:java -Dexec.mainClass=\"com.app.App\"\n```\n", encoding="utf-8")
            created_files.extend(["pom.xml", "src/main/java/com/app/App.java", "src/test/java/com/app/AppTest.java", "README.md"])

        elif template in ("c", "c_lang"):
            inc_dir = proj_dir / "include"
            inc_dir.mkdir(exist_ok=True)
            app_h = """#ifndef APP_H
#define APP_H

void print_greeting(const char *name);
int add_numbers(int a, int b);

#endif
"""
            (inc_dir / "app.h").write_text(app_h, encoding="utf-8")

            src_dir = proj_dir / "src"
            src_dir.mkdir(exist_ok=True)
            app_c = """#include <stdio.h>
#include "app.h"

void print_greeting(const char *name) {
    printf("Hello, %s! Welcome to C project.\\n", name);
}

int add_numbers(int a, int b) {
    return a + b;
}
"""
            (src_dir / "app.c").write_text(app_c, encoding="utf-8")

            main_c = f"""#include <stdio.h>
#include "app.h"

int main() {{
    print_greeting("{project_name}");
    printf("Result of 5 + 7 = %d\\n", add_numbers(5, 7));
    return 0;
}}
"""
            (src_dir / "main.c").write_text(main_c, encoding="utf-8")

            makefile = f"""CC = gcc
CFLAGS = -Wall -Wextra -Iinclude -O2

all: {project_name}

{project_name}: src/main.c src/app.c
\t$(CC) $(CFLAGS) -o $@ src/main.c src/app.c

clean:
\trm -f {project_name} *.o
"""
            (proj_dir / "Makefile").write_text(makefile, encoding="utf-8")
            (proj_dir / "README.md").write_text(f"# {project_name}\n\nModular C Project.\n\n## Build & Run\n```bash\ngcc -Iinclude -o {project_name} src/main.c src/app.c\n./{project_name}\n```\n", encoding="utf-8")
            created_files.extend(["include/app.h", "src/app.c", "src/main.c", "Makefile", "README.md"])

        elif template in ("cpp", "c++", "cplusplus"):
            inc_dir = proj_dir / "include"
            inc_dir.mkdir(exist_ok=True)
            app_hpp = """#pragma once
#include <string>

class Greeter {
public:
    explicit Greeter(std::string name);
    void greet() const;
    int calculate(int a, int b) const;
private:
    std::string name_;
};
"""
            (inc_dir / "app.hpp").write_text(app_hpp, encoding="utf-8")

            src_dir = proj_dir / "src"
            src_dir.mkdir(exist_ok=True)
            app_cpp = """#include "app.hpp"
#include <iostream>

Greeter::Greeter(std::string name) : name_(std::move(name)) {}

void Greeter::greet() const {
    std::cout << "Hello from C++ project: " << name_ << std::endl;
}

int Greeter::calculate(int a, int b) const {
    return a * b;
}
"""
            (src_dir / "app.cpp").write_text(app_cpp, encoding="utf-8")

            main_cpp = f"""#include "app.hpp"
#include <iostream>

int main() {{
    Greeter greeter("{project_name}");
    greeter.greet();
    std::cout << "Multiplication 6 * 7 = " << greeter.calculate(6, 7) << std::endl;
    return 0;
}}
"""
            (src_dir / "main.cpp").write_text(main_cpp, encoding="utf-8")

            cmakelists = f"""cmake_minimum_required(VERSION 3.15)
project({project_name} CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include_directories(include)

add_executable({project_name} src/main.cpp src/app.cpp)
"""
            (proj_dir / "CMakeLists.txt").write_text(cmakelists, encoding="utf-8")
            (proj_dir / "README.md").write_text(f"# {project_name}\n\nModern C++17 Project.\n\n## Build with CMake or g++\n```bash\ng++ -std=c++17 -Iinclude -o {project_name} src/main.cpp src/app.cpp\n./{project_name}\n```\n", encoding="utf-8")
            created_files.extend(["include/app.hpp", "src/app.cpp", "src/main.cpp", "CMakeLists.txt", "README.md"])

        elif template in ("sql", "database"):
            schema_sql = """-- Database Schema Definition
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    stock INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (product_id) REFERENCES products(id)
);
"""
            (proj_dir / "schema.sql").write_text(schema_sql, encoding="utf-8")

            seed_sql = """-- Seed Sample Data
INSERT OR IGNORE INTO users (username, email) VALUES
('alice', 'alice@example.com'),
('bob', 'bob@example.com'),
('charlie', 'charlie@example.com');

INSERT OR IGNORE INTO products (name, price, stock) VALUES
('Laptop', 999.99, 15),
('Wireless Mouse', 24.99, 100),
('Mechanical Keyboard', 79.99, 50);

INSERT OR IGNORE INTO orders (user_id, product_id, quantity) VALUES
(1, 1, 1),
(1, 2, 2),
(2, 3, 1),
(3, 2, 5);
"""
            (proj_dir / "seed.sql").write_text(seed_sql, encoding="utf-8")

            queries_sql = """-- Analytical Queries
-- 1. Total revenue and items ordered per user
SELECT 
    u.username,
    COUNT(o.id) AS total_orders,
    SUM(o.quantity * p.price) AS total_spent
FROM users u
JOIN orders o ON u.id = o.user_id
JOIN products p ON o.product_id = p.id
GROUP BY u.id, u.username
ORDER BY total_spent DESC;

-- 2. Low stock inventory alert
SELECT name, stock, price FROM products WHERE stock < 20;
"""
            (proj_dir / "queries.sql").write_text(queries_sql, encoding="utf-8")

            init_db_py = """import sqlite3
from pathlib import Path

def init():
    db_file = Path("database.db")
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    with open("schema.sql", "r", encoding="utf-8") as f:
        cursor.executescript(f.read())
    with open("seed.sql", "r", encoding="utf-8") as f:
        cursor.executescript(f.read())

    conn.commit()
    print("Database initialized and seeded successfully in database.db")

    print("\\nExecuting analytical query:")
    with open("queries.sql", "r", encoding="utf-8") as f:
        queries = f.read().split(";")
        for q in queries:
            q_clean = q.strip()
            if q_clean and not q_clean.startswith("--"):
                try:
                    cursor.execute(q_clean)
                    rows = cursor.fetchall()
                    if rows:
                        print("Query result:")
                        for r in rows:
                            print(" ", r)
                except Exception as e:
                    pass

    conn.close()

if __name__ == "__main__":
    init()
"""
            (proj_dir / "init_db.py").write_text(init_db_py, encoding="utf-8")
            (proj_dir / "README.md").write_text(f"# {project_name}\n\nSQL Database Architecture and Seed Kit.\n\n## Setup & Run\n```bash\npython init_db.py\n```\n", encoding="utf-8")
            created_files.extend(["schema.sql", "seed.sql", "queries.sql", "init_db.py", "README.md"])

        else:
            (proj_dir / "README.md").write_text(f"# {project_name}\n\nProject initialized with {template} template.\n", encoding="utf-8")
            created_files.append("README.md")

        return {
            "success": True,
            "project_name": project_name,
            "template": template,
            "directory": str(proj_dir),
            "files_created": created_files,
            "message": f"Scaffolded {template} project '{project_name}' in {proj_dir}"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_tests(project_dir: str, command: Optional[str] = None) -> Dict[str, Any]:
    """Runs test suite in the specified project directory."""
    try:
        p_dir = Path(os.path.expandvars(project_dir)).resolve()
        if not p_dir.exists():
            return {"success": False, "error": f"Project directory does not exist: {p_dir}"}

        test_cmd = command or "pytest"
        res = subprocess.run(
            test_cmd,
            shell=True,
            cwd=str(p_dir),
            capture_output=True,
            text=True,
            timeout=60
        )
        return {
            "success": res.returncode == 0,
            "command": test_cmd,
            "exit_code": res.returncode,
            "stdout": res.stdout.strip(),
            "stderr": res.stderr.strip()
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def fix_and_rerun(project_dir: str, files_to_patch: List[Dict[str, str]], test_command: Optional[str] = None) -> Dict[str, Any]:
    """
    Applies code fixes to files and re-runs test suite to verify resolution.
    files_to_patch: [{"path": "relative/path.py", "content": "new full content"}]
    """
    try:
        p_dir = Path(os.path.expandvars(project_dir)).resolve()
        for patch in files_to_patch:
            target = p_dir / patch["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(patch["content"], encoding="utf-8")

        test_res = run_tests(str(p_dir), command=test_command)
        return {
            "success": test_res["success"],
            "patches_applied": len(files_to_patch),
            "test_result": test_res
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
