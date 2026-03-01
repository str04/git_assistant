import requests
import base64
import json as _json
from config import GITHUB_API, get_github_headers

# File extensions to read for analysis
CODE_EXTENSIONS = [
    '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.go', '.rs', '.rb', '.php',
    '.ipynb', '.r', '.rmd', '.sql',
    '.md', '.txt', '.yaml', '.yml', '.toml', '.cfg', '.ini',
    '.csv', '.json', '.xls', '.xlsx'
]
SKIP_FILES = ['package-lock.json', 'yarn.lock', '.min.js', '.min.css', '__pycache__', '.pyc', 'README.md']


def should_skip(filename: str) -> bool:
    return any(skip in filename for skip in SKIP_FILES)


def extract_notebook_summary(content: str, filename: str) -> str:
    """Extract a compact summary from a Jupyter notebook."""
    try:
        nb = _json.loads(content)
        cells = nb.get("cells", [])

        imports = []
        code_snippets = []
        markdown_titles = []

        for cell in cells:
            src = "".join(cell.get("source", []))
            if not src.strip():
                continue

            if cell["cell_type"] == "markdown":
                # Get headings only
                for line in src.split("\n"):
                    if line.startswith("#"):
                        markdown_titles.append(line.strip())

            elif cell["cell_type"] == "code":
                # Get import statements
                for line in src.split("\n"):
                    if line.startswith("import ") or line.startswith("from "):
                        imports.append(line.strip())
                # Get first meaningful code snippet (not imports)
                non_import_lines = [l for l in src.split("\n") if l.strip() and not l.startswith("import") and not l.startswith("from") and not l.startswith("#")]
                if non_import_lines:
                    code_snippets.append("\n".join(non_import_lines[:5]))

        summary = f"📓 NOTEBOOK: {filename}\n"
        if markdown_titles:
            summary += f"  Sections: {' | '.join(markdown_titles[:6])}\n"
        if imports:
            unique_imports = list(dict.fromkeys(imports))[:12]
            summary += f"  Libraries: {', '.join(unique_imports)}\n"
        if code_snippets:
            summary += f"  Key code:\n"
            for snippet in code_snippets[:3]:
                summary += f"    {snippet[:200]}\n"

        return summary

    except Exception:
        return f"📓 NOTEBOOK: {filename} (could not parse)\n"


def extract_file_summary(path: str, content: str) -> str:
    """Extract a compact summary from any file type."""
    ext = path.split('.')[-1].lower()

    if ext == 'ipynb':
        return extract_notebook_summary(content, path)

    elif ext == 'csv':
        lines = content.split('\n')
        header = lines[0] if lines else ''
        row_count = len(lines) - 1
        return f"📊 DATA FILE: {path}\n  Columns: {header}\n  Rows: ~{row_count}\n"

    elif ext in ['xls', 'xlsx']:
        return f"📊 EXCEL FILE: {path}\n  (Excel data file — likely contains dataset for analysis)\n"

    elif ext == 'py':
        # Extract functions, classes, imports
        functions = []
        classes = []
        imports = []
        for line in content.split('\n'):
            stripped = line.strip()
            if stripped.startswith('def '):
                functions.append(stripped.split('(')[0].replace('def ', ''))
            elif stripped.startswith('class '):
                classes.append(stripped.split('(')[0].replace('class ', '').replace(':', ''))
            elif stripped.startswith('import ') or stripped.startswith('from '):
                imports.append(stripped)

        summary = f"🐍 PYTHON FILE: {path}\n"
        if imports:
            summary += f"  Libraries: {', '.join(imports[:8])}\n"
        if classes:
            summary += f"  Classes: {', '.join(classes[:5])}\n"
        if functions:
            summary += f"  Functions: {', '.join(functions[:10])}\n"
        if not functions and not classes:
            summary += f"  Content preview: {content[:300]}\n"
        return summary

    elif ext in ['md', 'txt']:
        return f"📄 DOC FILE: {path}\n  Preview: {content[:200]}\n"

    else:
        return f"📁 FILE: {path}\n  Preview: {content[:200]}\n"


def get_repo_files_content(token: str, owner: str, repo: str, max_files: int = 10) -> dict:
    """
    Scans ALL files in the repo and builds a compact summary for each.
    Token-efficient: each file gets ~200-400 chars summary, not full content.
    """
    tree_resp = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/HEAD?recursive=1",
        headers=get_github_headers(token)
    )
    if tree_resp.status_code != 200:
        return {"success": False, "error": "Could not read repo structure"}

    tree = tree_resp.json().get("tree", [])

    # Get ALL matching files — no limit
    all_files = [
        f for f in tree
        if f["type"] == "blob"
        and any(f["path"].endswith(ext) for ext in CODE_EXTENSIONS)
        and not should_skip(f["path"])
    ]

    files_content = []
    for f in all_files:
        # Skip very large files (>500KB)
        if f.get("size", 0) > 500000:
            files_content.append({
                "path": f["path"],
                "content": f"📁 FILE: {f['path']} (too large to read, size: {f.get('size', 0)} bytes)\n"
            })
            continue

        resp = requests.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/contents/{f['path']}",
            headers=get_github_headers(token)
        )
        if resp.status_code == 200:
            data = resp.json()
            try:
                raw_content = base64.b64decode(data["content"]).decode("utf-8")
                # Build a compact smart summary for this file
                summary = extract_file_summary(f["path"], raw_content)
                files_content.append({
                    "path": f["path"],
                    "content": summary
                })
            except Exception as e:
                files_content.append({
                    "path": f["path"],
                    "content": f"📁 FILE: {f['path']} (binary or unreadable)\n"
                })

    return {
        "success": True,
        "files": files_content,
        "total_files_found": len(tree),
        "files_analyzed": len(files_content)
    }


def build_readme_prompt(owner: str, repo: str, files_data: dict) -> str:
    """Build a prompt for professional README generation covering ALL files."""
    files_text = ""
    for f in files_data["files"]:
        files_text += f["content"] + "\n"

    file_names = [f["path"] for f in files_data["files"]]

    return f"""You are a senior software engineer and technical writer at a top tech company.
Write a PROFESSIONAL, DETAILED README.md for this GitHub repository.

Repository: {owner}/{repo}
Total files analyzed: {files_data['files_analyzed']}
All files found: {', '.join(file_names)}

DETAILED FILE ANALYSIS:
{files_text}

STRICT RULES:
1. Cover EVERY file listed above — mention each one by name and what it does
2. NEVER write generic content — every sentence must be specific to THIS project
3. For notebooks: mention the ACTUAL libraries, sections, and analysis performed in each one
4. For data files: mention the ACTUAL columns and what the data represents
5. This README will be seen by recruiters — make it impressive and specific
6. Minimum 500 words of real content

Write the complete README.md with ALL these sections:

# [Project Title — based on actual content]

> [One powerful specific sentence about what this project does]

## 📋 Table of Contents

## 📖 Project Overview
(What this project does, what problem it solves — specific to these files)

## 📁 Repository Contents
(List and describe EVERY file: what each notebook does, what each data file contains)

## ✨ Key Features & Analysis
(Specific features from the actual code — minimum 6 points)

## 🗂️ Datasets
(Describe each data file: name, columns found, what it represents)

## 🧠 Methodology
(Step by step: what analysis is done in each notebook)

## 🛠️ Tech Stack
(All libraries found across ALL files)

## ⚙️ Installation
```bash
pip install [actual libraries found]
```

## 🚀 How to Run
(How to run each notebook)

## 📊 Results & Outputs

## 🤝 Contributing
## 📄 License

Generate the complete README now. Be specific, detailed, and cover every file."""


def build_test_prompt(file_path: str, file_content: str, language: str) -> str:
    """Build a prompt for test generation."""
    if language == "python":
        framework = "pytest"
    elif language in ["javascript", "typescript"]:
        framework = "Jest"
    else:
        framework = "appropriate testing framework"

    return f"""You are an expert software engineer specializing in test-driven development.
Write COMPREHENSIVE, PRODUCTION-READY unit tests for this code.

File: {file_path}

CODE:
{file_content}

Requirements:
- Use {framework}
- Test EVERY function and method in the file
- Happy path tests (normal valid inputs)
- Edge case tests (empty, null, zero, negative, very large values)
- Error case tests (invalid types, exceptions expected)
- Clear descriptive test names
- Brief comments for each test group
- Generate ONLY the test file code, no explanations

Make it thorough and production-ready."""


def detect_language(file_path: str) -> str:
    ext = file_path.split('.')[-1].lower()
    mapping = {
        'py': 'python', 'js': 'javascript', 'ts': 'typescript',
        'jsx': 'javascript', 'tsx': 'typescript', 'java': 'java',
        'go': 'go', 'rb': 'ruby', 'cpp': 'cpp', 'c': 'c',
    }
    return mapping.get(ext, 'python')


def get_test_file_path(file_path: str, language: str) -> str:
    parts = file_path.rsplit('.', 1)
    if language == 'python':
        return f"tests/test_{parts[0].split('/')[-1]}.py"
    elif language in ['javascript', 'typescript']:
        ext = parts[1] if len(parts) > 1 else 'js'
        return f"tests/{parts[0].split('/')[-1]}.test.{ext}"
    return f"tests/test_{file_path}"