#!/usr/bin/env python3
"""
Repogent CI/CD Agent
Monitors builds, analyzes failures, and communicates with PR Reviewer.
"""
import os
import sys
import json
import re
import requests
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path

# Import shared constants
from config_constants import (
    MAX_LOG_SIZE_BYTES,
    MAX_ERROR_DETAILS,
    HTTP_TIMEOUT_SECONDS,
    get_truncation_sizes,
    LOG_TRUNCATION_HEAD_RATIO,
    LOG_TRUNCATION_TAIL_RATIO
)

__version__ = "1.0.0"


class BuildLogAnalyzer:
    """Analyzes build logs to identify failures and root causes"""
    
    MAX_LOG_SIZE = MAX_LOG_SIZE_BYTES
    
    # Common error patterns
    ERROR_PATTERNS = {
        'test_failure': [
            r'FAIL.*?(\S+\.test\.\S+)',
            r'Test suite failed.*?(\S+)',
            r'(\d+) failed.*?(\d+) passed',
            r'Error: .*?at (\S+\.js:\d+)',
        ],
        'compile_error': [
            r'error TS\d+: (.*)',
            r'SyntaxError: (.*)',
            r'CompileError: (.*)',
            r'error: (.*) at line (\d+)',
        ],
        'dependency_error': [
            r'Cannot find module [\'"]([^\'"]+)[\'"]',
            r'Module not found: (.*)',
            r'Package (.*) not found',
            r'npm ERR! (.*)',
        ],
        'lint_error': [
            r'ESLint found (\d+) problem',
            r'\d+:\d+\s+error\s+(.*)',
            r'Lint failed with (\d+) error',
            r'pylint.*rated at',
            r'flake8.*error',
        ],
        'permission_error': [
            r'Permission denied',
            r'EACCES: permission denied',
            r'fatal: could not create work tree',
            r'Access denied for user',
        ],
        'network_error': [
            r'ENOTFOUND',
            r'ECONNREFUSED',
            r'ETIMEDOUT',
            r'network timeout',
            r'Could not resolve host',
            r'Failed to connect to',
        ],
        'docker_error': [
            r'ERROR: failed to solve: (.*)',
            r'docker: Error response from daemon',
            r'cannot connect to docker daemon',
            r'Error response from daemon',
        ],
        'env_error': [
            r'Error: Missing required environment variable: (\w+)',
            r'(\w+) is not defined',
            r'Environment variable (\w+) not set',
        ],
        'memory_error': [
            r'OutOfMemoryError',
            r'JavaScript heap out of memory',
            r'fatal error: runtime: out of memory',
        ],
        'timeout': [
            r'timeout of (\d+)ms exceeded',
            r'The operation was canceled',
            r'ETIMEDOUT',
        ]
    }
    
    def analyze(self, logs: str) -> Dict[str, Any]:
        """Analyze build logs and return structured failure info"""
        # Limit log size to prevent DoS with smart truncation
        # Strategy: Keep 20% from beginning (context) and 80% from end (errors)
        # Rationale: Build errors typically appear at the end of logs, while
        # the beginning provides valuable context about the build environment
        if len(logs) > self.MAX_LOG_SIZE:
            print(f"⚠️ Log too large ({len(logs)} bytes), truncating to {self.MAX_LOG_SIZE}", file=sys.stderr)
            truncation_marker = "\n\n... [middle section truncated] ...\n\n"
            marker_len = len(truncation_marker)
            
            # Ensure we have space for the marker
            if self.MAX_LOG_SIZE <= marker_len:
                # If MAX_LOG_SIZE is too small for marker, just truncate without marker
                logs = logs[:self.MAX_LOG_SIZE]
            else:
                # Use shared truncation logic for consistency
                head_size, tail_size = get_truncation_sizes(self.MAX_LOG_SIZE)
                # Verify the result won't exceed MAX_LOG_SIZE
                logs = logs[:head_size] + truncation_marker + logs[-tail_size:]
                # Double-check final size (defensive programming)
                if len(logs) > self.MAX_LOG_SIZE:
                    logs = logs[:self.MAX_LOG_SIZE]
        
        failure_type = self._detect_failure_type(logs)
        error_details = self._extract_error_details(logs, failure_type)
        failed_step = self._find_failed_step(logs)
        suggestions = self._generate_suggestions(failure_type, error_details)
        
        return {
            'failure_type': failure_type,
            'error_details': error_details,
            'failed_step': failed_step,
            'suggestions': suggestions,
            'severity': self._assess_severity(failure_type)
        }
    
    def _detect_failure_type(self, logs: str) -> str:
        """Detect the type of failure from logs"""
        for failure_type, patterns in self.ERROR_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, logs, re.IGNORECASE | re.MULTILINE):
                    return failure_type
        return 'unknown'
    
    def _extract_error_details(self, logs: str, failure_type: str) -> List[str]:
        """Extract specific error messages"""
        details = []
        patterns = self.ERROR_PATTERNS.get(failure_type, [])
        
        for pattern in patterns:
            matches = re.finditer(pattern, logs, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                details.append(match.group(0))
                if len(details) >= MAX_ERROR_DETAILS:
                    break
        
        return details[:MAX_ERROR_DETAILS]
    
    def _find_failed_step(self, logs: str) -> Optional[str]:
        """Find which CI step failed"""
        # Look for common CI step markers
        step_patterns = [
            r'##\[error\](.*)',
            r'Error: Process completed with exit code \d+',
            r'Run (.*)\n.*Error',
        ]
        
        for pattern in step_patterns:
            match = re.search(pattern, logs, re.MULTILINE)
            if match:
                return match.group(1) if match.lastindex else match.group(0)
        
        return None
    
    def _generate_suggestions(self, failure_type: str, error_details: List[str]) -> List[str]:
        """Generate fix suggestions based on failure type"""
        suggestions = {
            'test_failure': [
                "Review the failing test cases and fix the implementation",
                "Check if recent code changes broke the test assertions",
                "Run tests locally to reproduce: `npm test` or `pytest`"
            ],
            'compile_error': [
                "Fix syntax errors in the code",
                "Check for type errors if using TypeScript",
                "Ensure all imports are correct"
            ],
            'dependency_error': [
                "Install missing dependencies: `npm install` or `pip install -r requirements.txt`",
                "Check if package.json or requirements.txt is up to date",
                "Clear dependency cache and reinstall"
            ],
            'lint_error': [
                "Fix linting errors in the code",
                "Run linter locally: `npm run lint` or `pylint <file>`",
                "Consider using auto-fix: `eslint --fix` or `black .`",
                "Update linting rules if they're too strict"
            ],
            'permission_error': [
                "Check file/directory permissions",
                "Verify CI user has necessary access rights",
                "Ensure GitHub token has required scopes",
                "Check repository settings and protected branches"
            ],
            'network_error': [
                "Check network connectivity and DNS resolution",
                "Verify external service URLs are correct",
                "Check if external service is down or rate-limiting",
                "Add retry logic for transient network failures"
            ],
            'docker_error': [
                "Verify Dockerfile syntax",
                "Check if base image exists and is accessible",
                "Ensure Docker daemon is running"
            ],
            'env_error': [
                "Add missing environment variables to GitHub Secrets",
                "Check .env.example for required variables",
                "Verify environment variable names match"
            ],
            'memory_error': [
                "Increase memory limit in CI configuration",
                "Optimize code to use less memory",
                "Consider splitting large test suites"
            ],
            'timeout': [
                "Increase timeout limit in CI configuration",
                "Optimize slow operations",
                "Check for infinite loops or network issues"
            ]
        }
        
        return suggestions.get(failure_type, ["Review build logs for more details", "Contact DevOps team if issue persists"])
    
    def _assess_severity(self, failure_type: str) -> str:
        """Assess severity of the failure"""
        critical = ['memory_error', 'docker_error', 'permission_error']
        high = ['test_failure', 'compile_error', 'dependency_error']
        medium = ['lint_error', 'timeout', 'network_error']
        
        if failure_type in critical:
            return 'CRITICAL'
        elif failure_type in high:
            return 'HIGH'
        elif failure_type in medium:
            return 'MEDIUM'
        else:
            return 'LOW'


class CICDAgent:
    """Main CI/CD monitoring agent"""
    
    def __init__(self):
        self.github_token = os.environ.get('GITHUB_TOKEN')
        self.repo = os.environ.get('GITHUB_REPOSITORY')
        self.run_id = os.environ.get('GITHUB_RUN_ID')
        self.analyzer = BuildLogAnalyzer()
    
    def get_workflow_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get workflow run details from GitHub API"""
        if not self.github_token or not self.repo:
            return None
        
        url = f"https://api.github.com/repos/{self.repo}/actions/runs/{run_id}"
        headers = {
            'Authorization': f'Bearer {self.github_token}',
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'Repogent-CICD/1.0'
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            print(f"❌ Timeout getting workflow run (>{HTTP_TIMEOUT_SECONDS}s)", file=sys.stderr)
            return None
        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to get workflow run: {e}", file=sys.stderr)
            return None
        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse workflow run response: {e}", file=sys.stderr)
            return None
    
    def get_workflow_jobs(self, run_id: str) -> List[Dict[str, Any]]:
        """Get jobs for a workflow run"""
        if not self.github_token or not self.repo:
            return []
        
        url = f"https://api.github.com/repos/{self.repo}/actions/runs/{run_id}/jobs"
        headers = {
            'Authorization': f'Bearer {self.github_token}',
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'Repogent-CICD/1.0'
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json().get('jobs', [])
        except requests.exceptions.Timeout:
            print(f"❌ Timeout getting workflow jobs (>{HTTP_TIMEOUT_SECONDS}s)", file=sys.stderr)
            return []
        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to get workflow jobs: {e}", file=sys.stderr)
            return []
        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse workflow jobs response: {e}", file=sys.stderr)
            return []
    
    def get_job_logs(self, job_id: str) -> str:
        """Get logs for a specific job"""
        if not self.github_token or not self.repo:
            return ""
        
        url = f"https://api.github.com/repos/{self.repo}/actions/jobs/{job_id}/logs"
        headers = {
            'Authorization': f'Bearer {self.github_token}',
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'Repogent-CICD/1.0'
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.text
        except requests.exceptions.Timeout:
            print(f"❌ Timeout getting job logs (>{HTTP_TIMEOUT_SECONDS}s)", file=sys.stderr)
            return ""
        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to get job logs: {e}", file=sys.stderr)
            return ""
    
    def find_related_pr(self, workflow_run: Dict[str, Any]) -> Optional[int]:
        """Find PR number related to this workflow run"""
        # Check pull_requests array
        pull_requests = workflow_run.get('pull_requests', [])
        if pull_requests and isinstance(pull_requests, list) and len(pull_requests) > 0:
            pr_num = pull_requests[0].get('number')
            # Validate it's a valid integer
            if pr_num is not None and isinstance(pr_num, int) and pr_num > 0:
                return pr_num
        
        # Parse from head_branch
        head_branch = workflow_run.get('head_branch', '')
        # Common patterns: refs/pull/123/merge, refs/pulls/123/merge, pull/123/head, pulls/123
        match = re.search(r'pulls?/(\d+)', head_branch)
        if match:
            pr_num = int(match.group(1))
            # Validate it's a positive integer
            if pr_num > 0:
                return pr_num
        
        return None
    
    def get_commit_author(self, sha: str) -> Tuple[Optional[str], Optional[str]]:
        """Get commit author username and email"""
        if not self.github_token or not self.repo:
            return None, None
        
        url = f"https://api.github.com/repos/{self.repo}/commits/{sha}"
        headers = {
            'Authorization': f'Bearer {self.github_token}',
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'Repogent-CICD/1.0'
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT_SECONDS)
            response.raise_for_status()
            data = response.json()
            
            # Safely extract author info with chained gets
            author_login = None
            author_email = None
            
            author_obj = data.get('author')
            if author_obj and isinstance(author_obj, dict):
                author_login = author_obj.get('login')
            
            commit_obj = data.get('commit')
            if commit_obj and isinstance(commit_obj, dict):
                commit_author = commit_obj.get('author')
                if commit_author and isinstance(commit_author, dict):
                    author_email = commit_author.get('email')
            
            return author_login, author_email
        except requests.exceptions.Timeout:
            print(f"❌ Timeout getting commit author (>{HTTP_TIMEOUT_SECONDS}s)", file=sys.stderr)
            return None, None
        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to get commit author: {e}", file=sys.stderr)
            return None, None
        except (json.JSONDecodeError, KeyError) as e:
            print(f"❌ Failed to parse commit author response: {e}", file=sys.stderr)
            return None, None
    
    def send_to_orchestrator(self, message_type: str, payload: Dict[str, Any]):
        """Send message to orchestrator"""
        # Import here to avoid circular dependency
        from orchestrator import Orchestrator, Message
        
        orchestrator = Orchestrator()
        message = Message(
            sender='cicd_agent',
            receiver='orchestrator',
            message_type=message_type,
            payload=payload
        )
        orchestrator.message_queue.enqueue(message)
    
    def analyze_failure(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Analyze a failed workflow run"""
        # Get workflow run details
        workflow_run = self.get_workflow_run(run_id)
        if not workflow_run:
            return None
        
        # Check if it actually failed
        conclusion = workflow_run.get('conclusion')
        if conclusion != 'failure':
            print(f"ℹ️ Workflow conclusion: {conclusion}", file=sys.stderr)
            return None
        
        # Get jobs
        jobs = self.get_workflow_jobs(run_id)
        failed_jobs = [job for job in jobs if job.get('conclusion') == 'failure']
        
        if not failed_jobs:
            return None
        
        # Analyze first failed job (usually most relevant)
        failed_job = failed_jobs[0]
        job_id = failed_job.get('id')
        if job_id is None:
            print(f"⚠️ Failed job has no ID, cannot fetch logs", file=sys.stderr)
            return None
        logs = self.get_job_logs(str(job_id))
        
        # Analyze logs
        analysis = self.analyzer.analyze(logs)
        
        # Get related PR
        pr_number = self.find_related_pr(workflow_run)
        
        # Get commit author
        head_sha = workflow_run.get('head_sha')
        author, author_email = self.get_commit_author(head_sha) if head_sha else (None, None)
        
        return {
            'run_id': run_id,
            'pr_number': pr_number,
            'workflow_name': workflow_run.get('name'),
            'head_sha': head_sha,
            'author': author,
            'author_email': author_email,
            'failed_job': failed_job.get('name'),
            'job_url': failed_job.get('html_url'),
            'analysis': analysis,
            'timestamp': datetime.now().isoformat()
        }
    
    def post_failure_comment(self, pr_number: int, failure_data: Dict[str, Any]):
        """Post failure analysis as PR comment"""
        if not self.github_token or not self.repo or not pr_number:
            return False
        
        analysis = failure_data.get('analysis', {})
        severity_emoji = {'CRITICAL': '🔴', 'HIGH': '🟠', 'MEDIUM': '🟡'}.get(
            analysis.get('severity', 'MEDIUM'), '🟡'
        )
        
        # Format comment
        comment = f"""## {severity_emoji} CI/CD Build Failed

**Workflow:** {failure_data.get('workflow_name', 'Unknown')}  
**Failed Job:** {failure_data.get('failed_job', 'Unknown')}  
**Failure Type:** `{analysis.get('failure_type', 'unknown')}`

### 🔍 Error Details:
"""
        
        error_details = analysis.get('error_details', [])
        if error_details:
            for detail in error_details[:3]:  # Show top 3
                comment += f"```\n{detail}\n```\n"
        else:
            comment += "*No specific error details extracted*\n"
        
        comment += "\n### 💡 Suggested Fixes:\n"
        suggestions = analysis.get('suggestions', [])
        for i, suggestion in enumerate(suggestions, 1):
            comment += f"{i}. {suggestion}\n"
        
        comment += f"\n### 📊 Build Information:\n"
        # Safely slice SHA - handle None case
        head_sha = failure_data.get('head_sha', 'Unknown')
        sha_display = head_sha[:7] if head_sha and isinstance(head_sha, str) else 'Unknown'
        comment += f"- **Commit:** `{sha_display}`\n"
        if failure_data.get('author'):
            comment += f"- **Author:** @{failure_data['author']}\n"
        comment += f"- **Job URL:** {failure_data.get('job_url', 'N/A')}\n"
        
        comment += "\n---\n*🤖 Analysis by Repogent CI/CD Agent*"
        
        # Post comment
        url = f"https://api.github.com/repos/{self.repo}/issues/{pr_number}/comments"
        headers = {
            'Authorization': f'Bearer {self.github_token}',
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'Repogent-CICD/1.0'
        }
        
        try:
            response = requests.post(url, headers=headers, json={'body': comment}, timeout=HTTP_TIMEOUT_SECONDS)
            response.raise_for_status()
            print(f"✅ Posted failure analysis to PR #{pr_number}", file=sys.stderr)
            return True
        except requests.exceptions.Timeout:
            print(f"❌ Timeout posting comment (>{HTTP_TIMEOUT_SECONDS}s)", file=sys.stderr)
            return False
        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to post comment: {e}", file=sys.stderr)
            return False


def main():
    """Main entry point for CI/CD agent"""
    agent = CICDAgent()
    
    # Get workflow run ID from environment
    run_id = os.environ.get('WORKFLOW_RUN_ID') or os.environ.get('GITHUB_RUN_ID')
    
    if not run_id:
        print("❌ No workflow run ID provided", file=sys.stderr)
        sys.exit(1)
    
    print(f"🔍 CI/CD Agent analyzing workflow run: {run_id}", file=sys.stderr)
    
    # Analyze the failure
    failure_data = agent.analyze_failure(run_id)
    
    if not failure_data:
        print("ℹ️ No failure detected or unable to analyze", file=sys.stderr)
        sys.exit(0)
    
    print(f"🐛 Failure detected: {failure_data['analysis']['failure_type']}", file=sys.stderr)
    
    # Send to orchestrator
    agent.send_to_orchestrator('build_failure', failure_data)
    
    # Post comment if PR exists
    pr_number = failure_data.get('pr_number')
    if pr_number:
        agent.post_failure_comment(pr_number, failure_data)
    
    print("✅ CI/CD Agent completed analysis", file=sys.stderr)


if __name__ == '__main__':
    main()
