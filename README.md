# 🐙 GitHub Assistant

An AI-powered GitHub assistant that lets you manage your entire GitHub workflow through natural conversation.

Built with **Groq AI**, **Streamlit**, and the **GitHub API**.

🔗 **Live Demo:** [str04-git-assistant-app-40kkl5.streamlit.app](https://str04-git-assistant-app-40kkl5.streamlit.app)

---

## ✨ Features

### 🤖 Core Agent
- Natural language interface — just describe what you want to do
- Powered by Groq's free LLaMA 3.3 70B model
- Persistent chat history per user session
- Multi-user support — each user has their own private account and chats

### 📁 Repository Management
- Create, delete, list, and inspect repositories
- Fork repositories from any user
- Upload multiple local files directly to any repo and branch

### 🌿 Branch Management
- Create and delete branches
- Merge branches
- List all branches in a repo

### 📝 File Operations
- Read, create, update, and delete files
- Smart file editor — edit specific lines, insert, delete, find & replace, append
- Preview large files before editing (token efficient)
- List files and commit history

### 🔀 Pull Requests
- Create, list, merge, and close pull requests
- Add comments to PRs

### 🐛 Issues
- Create, list, and close issues
- Add comments and labels to issues

### 🔍 Search
- Search repositories and code across GitHub
- Get repo summaries and user profiles

---

## 🛠️ Tech Stack

| Component | Technology |
|---|---|
| Frontend | Streamlit |
| AI Model | Groq API — LLaMA 3.3 70B |
| GitHub Integration | GitHub REST API |
| Database | SQLite (per-user chat history) |
| Auth | Browser cookies (30-day persistence) |
| Deployment | Streamlit Cloud |

---

## 🔒 Privacy & Security

- Your GitHub token is stored **only in your browser** as a cookie — never shared with other users
- Each user's chat history is isolated by a hashed user ID in the database
- The Groq API key is stored server-side as a Streamlit secret — never exposed to users
- `.env` and `agent.db` are excluded from version control via `.gitignore`

---

## 📄 License

MIT License — free to use and modify.
