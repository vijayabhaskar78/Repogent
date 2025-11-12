#!/usr/bin/env python3
"""
Respond to Comment Script - GitHub Actions version
Provides intelligent responses to issue comments
"""
import os
import sys
import json
from groq import Groq

def get_issue_comments(token, repo, issue_number):
    """Get all comments from the issue, excluding bot comments"""
    import requests
    
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github+json'
    }
    
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    
    comments = response.json()
    conversation = []
    for comment in comments:
        # Safe dict access with validation
        if not isinstance(comment, dict):
            continue
        
        user = comment.get('user', {})
        if not isinstance(user, dict):
            continue
            
        author = user.get('login', 'unknown')
        body = comment.get('body', '')
        created_at = comment.get('created_at', '')
        
        # Skip bot comments to avoid circular context
        if 'bot' not in author.lower() and author != 'github-actions[bot]':
            conversation.append({
                'author': author,
                'body': body,
                'created_at': created_at
            })
    return conversation

def generate_response(client, issue_title, issue_body, comment_body, conversation_history):
    """Generate intelligent response using Groq"""
    
    # Build conversation context
    context = f"Issue Title: {issue_title}\n\nIssue Description:\n{issue_body}\n\n"
    
    if conversation_history:
        context += "Previous Comments:\n"
        for msg in conversation_history[-5:]:  # Last 5 comments
            author = msg.get('author', 'unknown')
            body = msg.get('body', '')
            # Safely slice with bounds check
            body_preview = body[:200] if body else '(no content)'
            context += f"- {author}: {body_preview}\n"
    
    system_prompt = """You are Repogent, a helpful AI assistant for GitHub repositories. 
Your role is to provide helpful, technical responses to issue comments.

Guidelines:
- Be concise and technical
- Provide actionable advice when possible
- Ask clarifying questions if needed
- Reference code, documentation, or error messages
- Be friendly but professional

Keep responses under 300 words."""

    user_content = f"""{context}

Latest Comment: {comment_body}

Please provide a helpful response to this comment."""

    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            model=os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile'),
            max_tokens=1024,
            temperature=0.7
        )
        
        if not response.choices or len(response.choices) == 0:
            print(f"⚠️ No response choices from LLM", file=sys.stderr)
            return None
        
        content = response.choices[0].message.content
        if not content:
            print(f"⚠️ Empty response content from LLM", file=sys.stderr)
            return None
        
        return content.strip()
        
    except Exception as e:
        print(f"❌ Response generation error: {e}", file=sys.stderr)
        return None

def post_comment(token, repo, issue_number, body):
    """Post a comment to the issue"""
    import requests
    
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github+json'
    }
    
    response = requests.post(url, headers=headers, json={'body': body}, timeout=30)
    response.raise_for_status()
    return response.json()

def main():
    # Get environment variables
    groq_api_key = os.environ.get('GROQ_API_KEY')
    github_token = os.environ.get('GITHUB_TOKEN')
    repo = os.environ.get('GITHUB_REPOSITORY')
    issue_number = os.environ.get('ISSUE_NUMBER')
    comment_body = os.environ.get('COMMENT_BODY', '')
    issue_title = os.environ.get('ISSUE_TITLE', '')
    issue_body = os.environ.get('ISSUE_BODY', '')
    
    if not all([groq_api_key, github_token, repo, issue_number, comment_body]):
        print("Missing required environment variables", file=sys.stderr)
        sys.exit(1)
    
    # Initialize Groq client
    client = Groq(api_key=groq_api_key)
    
    print(f"💬 Responding to comment on issue #{issue_number}", file=sys.stderr)
    
    # Get conversation history
    try:
        conversation = get_issue_comments(github_token, repo, issue_number)
    except Exception as e:
        print(f"⚠️ Could not fetch conversation history: {e}", file=sys.stderr)
        conversation = []
    
    # Generate response
    response_text = generate_response(client, issue_title, issue_body, comment_body, conversation)
    
    if not response_text:
        print("❌ Failed to generate response", file=sys.stderr)
        sys.exit(1)
    
    # Limit response length to prevent abuse
    if len(response_text) > 5000:
        response_text = response_text[:5000] + "\n\n... (response truncated for length)"
    
    # Format response with signature
    formatted_response = f"""{response_text}

---
*🤖 Response generated by Repogent AI powered by Groq*"""
    
    # Post comment
    try:
        post_comment(github_token, repo, issue_number, formatted_response)
        print(f"✅ Posted response", file=sys.stderr)
    except Exception as e:
        print(f"❌ Failed to post comment: {e}", file=sys.stderr)
        sys.exit(1)
    
    print(f"🎉 Successfully responded to comment on issue #{issue_number}", file=sys.stderr)

if __name__ == '__main__':
    main()
