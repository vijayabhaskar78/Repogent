#!/usr/bin/env python3
"""
Shared Configuration Constants for Repogent
Centralized configuration to avoid magic numbers across modules.
"""

__version__ = "1.0.0"

# ============================================================================
# LLM Model Configuration
# ============================================================================

# Primary model for all tasks
# llama-3.3-70b-versatile: Latest model for all tasks (PR review, issue triage, Q&A, responses)
# Note: llama-3.1-8b-instant has been decommissioned
MODEL_PR_REVIEW = "llama-3.3-70b-versatile"
MODEL_ISSUE_TRIAGE = "llama-3.3-70b-versatile"
MODEL_COMMUNITY_QA = "llama-3.3-70b-versatile"
MODEL_COMMENT_RESPONSE = "llama-3.3-70b-versatile"

# ============================================================================
# Size Limits
# ============================================================================

# Message queue limits
MAX_PAYLOAD_SIZE_BYTES = 512 * 1024  # 512KB max payload per message
MAX_QUEUE_DEPTH = 100  # Maximum messages in queue before eviction

# Context storage limits
MAX_CONTEXT_SIZE_BYTES = 1024 * 1024  # 1MB per context file
MAX_CONTEXT_FILES = 1000  # Maximum number of context files

# File processing limits
MAX_FILE_SIZE = 100 * 1024  # 100KB limit per file for indexing
MAX_TOTAL_INDEX_SIZE = 50 * 1024 * 1024  # 50MB total index size
MAX_INDEX_FILES = 400  # Maximum files to index
MAX_LOG_SIZE_BYTES = 1024 * 1024  # 1MB max log size to analyze

# Response limits
MAX_RESPONSE_LENGTH = 65000  # Maximum response length in characters
MAX_ERROR_DETAILS = 5  # Maximum error details to extract

# ============================================================================
# Timeout Configuration
# ============================================================================

HTTP_TIMEOUT_SECONDS = 30  # Timeout for HTTP requests to GitHub API/Groq

# ============================================================================
# Search and Display Configuration
# ============================================================================

CONTEXT_LINES = 5  # Lines before/after a code match in search results
MAX_SEARCH_RESULTS = 5  # Maximum search results to return
MAX_CONVERSATION_CONTEXT = 5  # Maximum previous comments to include

# ============================================================================
# Log Processing Configuration
# ============================================================================

# Log truncation strategy for large build logs
# Keep beginning for context and end for errors
LOG_TRUNCATION_HEAD_RATIO = 0.2  # 20% from start
LOG_TRUNCATION_TAIL_RATIO = 0.8  # 80% from end (errors typically at end)

# ============================================================================
# File Extensions and Exclusions
# ============================================================================

# File extensions to index for code search
CODE_EXTENSIONS = {'.py', '.js', '.ts', '.yaml', '.yml', '.json', '.md', '.txt'}

# Directories to skip during indexing
SKIP_DIRS = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'dist', 'build'}

# ============================================================================
# Helper Functions
# ============================================================================

def get_model_for_task(task: str) -> str:
    """
    Get the recommended model for a specific task.
    
    Args:
        task: One of 'pr_review', 'issue_triage', 'community_qa', 'comment_response'
    
    Returns:
        Model name string (currently all tasks use llama-3.3-70b-versatile)
    """
    # All tasks now use the same model since llama-3.1-8b-instant is decommissioned
    models = {
        'pr_review': MODEL_PR_REVIEW,
        'issue_triage': MODEL_ISSUE_TRIAGE,
        'community_qa': MODEL_COMMUNITY_QA,
        'comment_response': MODEL_COMMENT_RESPONSE,
    }
    return models.get(task, MODEL_PR_REVIEW)


def get_truncation_sizes(total_size: int) -> tuple:
    """
    Calculate head and tail sizes for log truncation.
    
    Args:
        total_size: Total size of content to truncate
    
    Returns:
        Tuple of (head_size, tail_size)
    """
    if total_size <= MAX_LOG_SIZE_BYTES:
        return total_size, 0
    
    truncation_marker_len = len("\n\n... [middle section truncated] ...\n\n")
    available = MAX_LOG_SIZE_BYTES - truncation_marker_len
    
    head_size = int(available * LOG_TRUNCATION_HEAD_RATIO)
    tail_size = available - head_size
    
    return head_size, tail_size
