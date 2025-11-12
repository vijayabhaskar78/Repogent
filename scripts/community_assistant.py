#!/usr/bin/env python3
"""
Repogent Community Assistant
Helps users navigate the codebase by answering questions with code references and permalinks.
"""
import os
import sys
import json
import re
from pathlib import Path
from groq import Groq
import requests

__version__ = "1.0.0"

# File extensions to index
CODE_EXTENSIONS = {'.py', '.js', '.ts', '.yaml', '.yml', '.json', '.md', '.txt'}
MAX_FILE_SIZE = 100000  # 100KB limit per file


def index_codebase(repo_path='.'):
    """
    Index all relevant files in the codebase.
    Returns a dict mapping file paths to their content and line info.
    """
    indexed_files = {}
    repo_path = Path(repo_path)
    total_size = 0
    max_total_size = 50 * 1024 * 1024  # 50MB total limit
    max_files = 500  # Maximum 500 files
    
    # Directories to skip
    skip_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'dist', 'build'}
    
    for file_path in repo_path.rglob('*'):
        # Check if we've hit limits
        if len(indexed_files) >= max_files:
            print(f"⚠️ Reached file limit ({max_files}), stopping indexing", file=sys.stderr)
            break
        if total_size >= max_total_size:
            print(f"⚠️ Reached size limit ({max_total_size} bytes), stopping indexing", file=sys.stderr)
            break
        # Skip directories, symlinks, and excluded paths
        if file_path.is_dir() or file_path.is_symlink():
            continue
        if any(skip in file_path.parts for skip in skip_dirs):
            continue
        if file_path.suffix not in CODE_EXTENSIONS:
            continue
        
        try:
            # Check file size
            if file_path.stat().st_size > MAX_FILE_SIZE:
                continue
            
            # Read file content
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Get relative path from repo root
            rel_path = file_path.relative_to(repo_path)
            
            # Store file info
            file_size = len(content)
            indexed_files[str(rel_path)] = {
                'content': content,
                'lines': content.split('\n'),
                'size': file_size
            }
            total_size += file_size
            
        except (UnicodeDecodeError, PermissionError, OSError):
            # Skip files we can't read
            continue
    
    print(f"📊 Indexed {len(indexed_files)} files ({total_size / 1024:.1f} KB total)", file=sys.stderr)
    return indexed_files


def search_codebase(indexed_files, query, max_results=5):
    """
    Search indexed files for relevant code sections.
    Returns list of matches with file path, line numbers, and content.
    """
    results = []
    query_lower = query.lower()
    
    # Extract keywords from query
    keywords = re.findall(r'\b\w+\b', query_lower)
    
    # Filter out common stop words
    stop_words = {'the', 'is', 'at', 'which', 'on', 'a', 'an', 'and', 'or', 'but', 'in', 'with', 'to', 'for', 'of', 'as', 'by', 'how', 'what', 'where', 'when', 'why', 'does', 'do'}
    keywords = [kw for kw in keywords if kw not in stop_words and len(kw) > 2]
    
    # If no valid keywords, return empty
    if not keywords:
        return []
    
    for file_path, file_info in indexed_files.items():
        lines = file_info['lines']
        content_lower = file_info['content'].lower()
        
        # Check if file is relevant (contains keywords)
        relevance_score = sum(1 for kw in keywords if kw in content_lower)
        if relevance_score == 0:
            continue
        
        # Find specific line ranges that match
        matches = []
        seen_ranges = set()  # Track ranges to avoid duplicates
        
        for i, line in enumerate(lines):
            line_lower = line.lower()
            if any(kw in line_lower for kw in keywords):
                # Get context (5 lines before and after)
                start_line = max(0, i - 5)
                end_line = min(len(lines), i + 6)
                
                # Check if this range overlaps with existing ones
                range_key = (file_path, start_line, end_line)
                if range_key in seen_ranges:
                    continue
                seen_ranges.add(range_key)
                
                match = {
                    'file': file_path,
                    'start_line': start_line + 1,  # 1-indexed for GitHub
                    'end_line': end_line,  # Already correct (min(len(lines), i+6) gives us the right exclusive end)
                    'matched_line': i + 1,
                    'snippet': '\n'.join(lines[start_line:end_line]),
                    'relevance': relevance_score
                }
                matches.append(match)
        
        # Add top matches from this file
        if matches:
            # Sort by relevance and proximity to matched line
            matches.sort(key=lambda x: x['relevance'], reverse=True)
            results.extend(matches[:2])  # Top 2 matches per file
    
    # Sort all results by relevance
    results.sort(key=lambda x: x['relevance'], reverse=True)
    return results[:max_results]


def generate_permalink(repo_owner, repo_name, branch, file_path, start_line, end_line):
    """Generate GitHub permalink to specific lines in a file"""
    base_url = f"https://github.com/{repo_owner}/{repo_name}/blob/{branch}/{file_path}"
    
    if start_line == end_line:
        return f"{base_url}#L{start_line}"
    else:
        return f"{base_url}#L{start_line}-L{end_line}"


def get_repository_structure(indexed_files):
    """Get a summary of the repository structure"""
    structure = {}
    for file_path in indexed_files.keys():
        parts = Path(file_path).parts
        current = structure
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        current[parts[-1]] = None
    return structure


def build_context(search_results, repo_owner, repo_name, branch):
    """Build context string with search results and permalinks"""
    if not search_results:
        return "No relevant code found in the repository."
    
    context_parts = ["Here are the relevant code sections I found:\n"]
    
    for i, result in enumerate(search_results, 1):
        permalink = generate_permalink(
            repo_owner, repo_name, branch,
            result['file'],
            result['start_line'],
            result['end_line']
        )
        
        # Detect file extension for syntax highlighting
        file_ext = Path(result['file']).suffix
        lang_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.yaml': 'yaml',
            '.yml': 'yaml',
            '.json': 'json',
            '.md': 'markdown',
            '.sh': 'bash'
        }
        lang = lang_map.get(file_ext, '')
        
        context_parts.append(f"\n**{i}. `{result['file']}` (Lines {result['start_line']}-{result['end_line']})**")
        context_parts.append(f"🔗 {permalink}\n")
        context_parts.append(f"```{lang}\n{result['snippet']}\n```")
    
    return '\n'.join(context_parts)


def answer_question(client, question, indexed_files, repo_owner, repo_name, branch):
    """
    Answer user's question about the codebase using LLM with code context.
    """
    # Search for relevant code
    search_results = search_codebase(indexed_files, question, max_results=3)
    
    # Build context with code references
    code_context = build_context(search_results, repo_owner, repo_name, branch)
    
    # Get repository structure for overview
    file_list = list(indexed_files.keys())[:20]  # Top 20 files
    
    system_prompt = f"""You are Repogent Community Assistant, an AI helper for the {repo_name} repository.

Your role is to help users understand the codebase by:
1. Answering questions clearly and concisely
2. Referencing specific code sections with permalinks
3. Explaining how things work
4. Guiding users to relevant files and functions

Repository structure (key files):
{chr(10).join(f"- {f}" for f in file_list)}

When answering:
- Always reference the provided code snippets and permalinks
- Be specific about file locations and line numbers
- Explain technical concepts clearly
- Suggest where to look for more information
- If you're unsure, say so and point to relevant files

Keep responses concise but informative (max 500 words)."""

    user_content = f"""Question: {question}

{code_context}

Please answer the question using the code references above. Include the permalinks in your response."""

    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            model=os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile'),
            max_tokens=2048,
            temperature=0.3
        )
        
        if not response.choices or len(response.choices) == 0:
            raise ValueError("No response from LLM")
        
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty response content from LLM")
        
        return content.strip()
        
    except Exception as e:
        print(f"❌ Error generating answer: {e}", file=sys.stderr)
        # Fallback: return just the code context
        return f"I found these relevant code sections:\n\n{code_context}"


def post_comment(token, repo, issue_number, body):
    """Post a comment to the issue"""
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'Repogent-Bot/1.0'
    }
    
    response = requests.post(url, headers=headers, json={'body': body}, timeout=30)
    response.raise_for_status()
    return response.json()


def extract_question(comment_body):
    """
    Extract the actual question from a comment that mentions @repogent.
    Removes the @repogent mention and common prefixes.
    """
    # Remove @repogent mention
    question = re.sub(r'@repogent\s*', '', comment_body, flags=re.IGNORECASE)
    
    # Remove common prefixes
    question = re.sub(r'^(ask:|question:|help:)\s*', '', question, flags=re.IGNORECASE)
    
    return question.strip()


def main():
    # Get environment variables
    groq_api_key = os.environ.get('GROQ_API_KEY')
    github_token = os.environ.get('GITHUB_TOKEN')
    repo = os.environ.get('GITHUB_REPOSITORY')
    issue_number = os.environ.get('ISSUE_NUMBER')
    comment_body = os.environ.get('COMMENT_BODY', '')
    comment_author = os.environ.get('COMMENT_AUTHOR', '')
    
    if not all([groq_api_key, github_token, repo, issue_number]):
        print("Missing required environment variables", file=sys.stderr)
        sys.exit(1)
    
    # Skip if comment is from a bot
    if comment_author and ('bot' in comment_author.lower() or comment_author == 'github-actions[bot]'):
        print("Comment is from a bot, skipping to avoid loops", file=sys.stderr)
        sys.exit(0)
    
    # Check if comment mentions @repogent
    if '@repogent' not in comment_body.lower():
        print("Comment doesn't mention @repogent, skipping", file=sys.stderr)
        sys.exit(0)
    
    # Extract question
    question = extract_question(comment_body)
    if not question or len(question) < 5:
        print("No valid question found", file=sys.stderr)
        sys.exit(0)
    
    print(f"🤖 Processing question: {question}", file=sys.stderr)
    
    # Parse repo info with validation
    if '/' not in repo:
        print(f"❌ Invalid repository format: {repo}", file=sys.stderr)
        sys.exit(1)
    
    repo_parts = repo.split('/')
    if len(repo_parts) != 2:
        print(f"❌ Invalid repository format: {repo}", file=sys.stderr)
        sys.exit(1)
    
    repo_owner, repo_name = repo_parts[0], repo_parts[1]
    branch = os.environ.get('GITHUB_REF_NAME', 'main')
    
    # Initialize Groq client
    client = Groq(api_key=groq_api_key)
    
    # Index the codebase
    print("📚 Indexing codebase...", file=sys.stderr)
    indexed_files = index_codebase()
    print(f"✅ Indexed {len(indexed_files)} files", file=sys.stderr)
    
    # Answer the question
    print("🔍 Searching for relevant code...", file=sys.stderr)
    answer = answer_question(client, question, indexed_files, repo_owner, repo_name, branch)
    
    # Format response
    formatted_response = f"""🤖 **Repogent Community Assistant**

{answer}

---
*💡 Tip: Ask me questions like "How does X work?" or "Where is Y implemented?" and I'll search the codebase for you!*
*Powered by Groq AI*"""
    
    # Limit response length
    if len(formatted_response) > 65000:
        formatted_response = formatted_response[:65000] + "\n\n... (response truncated)"
    
    # Post comment
    try:
        post_comment(github_token, repo, issue_number, formatted_response)
        print(f"✅ Posted answer to issue #{issue_number}", file=sys.stderr)
    except Exception as e:
        print(f"❌ Failed to post comment: {e}", file=sys.stderr)
        sys.exit(1)
    
    print(f"🎉 Successfully answered question in issue #{issue_number}", file=sys.stderr)


if __name__ == '__main__':
    main()
