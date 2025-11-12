# Repogent Complete - Unified GitHub Repository Assistant

🤖 A comprehensive GitHub bot that combines PR review and issue management capabilities, all running as GitHub Actions.

## ✨ Features

### 🔍 PR Review (from pr-reviewer)
- **Inline code comments** on specific lines
- **Severity levels**: 🔴 Critical, 🟡 Warning, 🟢 Suggestion  
- **Smart fix suggestions** for every issue
- **Lightning-fast** reviews powered by Groq

### 🎯 Issue Management (from repogent-issue-manager)
- **Auto-triage & labeling** of new issues
- **AI-powered classification** (Bug, Enhancement, Question)
- **Intelligent responses** to issue comments
- **Context-aware** explanations

### 💬 Community Assistant (NEW!)
- **Ask questions about the codebase** using `@repogent`
- **Get code references** with highlighted permalinks
- **Navigate the repository** with AI guidance
- **Understand how features work** with code examples

## 🚀 Quick Start

### 1. Copy to Your Repository

```bash
# Copy workflows
cp -r .github/workflows /path/to/your/repo/.github/

# Copy scripts
cp -r scripts /path/to/your/repo/

# Copy config
cp -r config /path/to/your/repo/

# Copy requirements
cp requirements.txt /path/to/your/repo/
```

### 2. Add Secret

Go to: **Settings** → **Secrets** → **Actions**

Add: `GROQ_API_KEY` from https://console.groq.com

### 3. Enable Permissions

**Settings** → **Actions** → **General** → **Workflow permissions**

Select: ✅ **Read and write permissions**

## 📖 Usage

- **PR Review**: Open a PR → Get inline comments automatically
- **Issue Triage**: Create issue → Auto-labeled with explanation  
- **Smart Responses**: Comment on issue → AI responds
- **Community Help**: Mention `@repogent` with your question → Get answers with code references

### 🤖 Community Assistant Examples

Ask questions about the codebase by mentioning `@repogent`:

```
@repogent How does the diff parsing work?
@repogent Where is the severity emoji logic implemented?
@repogent Show me how to add a new label
@repogent What files handle GitHub API calls?
```

The bot will:
1. 🔍 Search the codebase for relevant code
2. 📍 Provide GitHub permalinks to specific lines
3. 💡 Explain how things work with context
4. 📝 Show code snippets with syntax highlighting

## 📂 Repository Structure

```
.github/workflows/
  ├── pr-review.yml              # PR review automation
  ├── issue-triage.yml           # Issue management
  └── community-assistant.yml    # Community Q&A helper
scripts/
  ├── review_pr.py               # PR analysis
  ├── post_review_comments.py    # Post inline PR comments
  ├── triage_issue.py            # Issue classification
  ├── respond_to_comment.py      # Issue comment responses
  └── community_assistant.py     # Codebase Q&A with references
config/
  └── labels.json                # Label configuration
```

## ⚙️ Configuration

Edit `config/labels.json`:
```json
{
  "labels": ["Bug", "Enhancement", "Question", "Documentation"],
  "default_label": "Question"
}
```

## 🔧 Models

- **PR Review**: llama-3.3-70b-versatile
- **Issue Triage**: llama-3.3-70b-versatile
- **Community Assistant**: llama-3.3-70b-versatile  

## 📄 License

Apache 2.0 License

## 👤 Author

vijayabhaskar78

---
**⚡ Powered by Groq**
