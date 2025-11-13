#!/usr/bin/env python3
"""
Integration Tests with Mocked GitHub API
Tests agent interactions with GitHub API using mocked responses.
"""
import sys
import json
import unittest
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path

print("🧪 INTEGRATION TEST SUITE - Mocked GitHub API")
print("=" * 60)

# Add scripts to path
sys.path.insert(0, 'scripts')


class MockResponse:
    """Mock HTTP response object"""
    def __init__(self, json_data=None, text_data="", status_code=200):
        self.json_data = json_data or {}
        self.text_data = text_data
        self.status_code = status_code
    
    def json(self):
        return self.json_data
    
    @property
    def text(self):
        return self.text_data
    
    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


class TestPostReviewComments(unittest.TestCase):
    """Test PR review comment posting with mocked GitHub API"""
    
    @patch('post_review_comments.requests.post')
    def test_post_review_success(self, mock_post):
        """Test successful review comment posting"""
        from post_review_comments import post_review_comments
        
        # Mock successful API response
        mock_post.return_value = MockResponse(
            json_data={'id': 123, 'state': 'commented'},
            status_code=200
        )
        
        reviews = [
            {
                'file': 'test.py',
                'line': 10,
                'severity': 'WARNING',
                'message': 'Test warning',
                'suggestion': 'Fix it'
            }
        ]
        
        diff_text = """diff --git a/test.py b/test.py
index 123..456 789
--- a/test.py
+++ b/test.py
@@ -1,3 +1,5 @@
+# New line
 def test():
     pass
"""
        
        result = post_review_comments(
            'fake-token',
            'owner/repo',
            1,
            'abc123',
            reviews,
            diff_text
        )
        
        self.assertTrue(result)
        self.assertTrue(mock_post.called)
    
    @patch('post_review_comments.requests.post')
    def test_post_review_api_error(self, mock_post):
        """Test handling of GitHub API errors"""
        from post_review_comments import post_review_comments
        import requests
        
        # Mock API error by raising exception
        mock_post.side_effect = requests.exceptions.RequestException("API Error")
        
        reviews = [{'file': 'test.py', 'line': 10, 'severity': 'INFO', 'message': 'Test'}]
        
        result = post_review_comments(
            'fake-token',
            'owner/repo',
            1,
            'abc123',
            reviews,
            ""
        )
        
        self.assertFalse(result)


class TestTriageIssue(unittest.TestCase):
    """Test issue triage with mocked GitHub API"""
    
    @patch('triage_issue.Groq')
    def test_triage_classification(self, mock_groq):
        """Test issue classification"""
        from triage_issue import classify_issue
        
        # Mock Groq response
        mock_client = MagicMock()
        mock_groq.return_value = mock_client
        
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = '{"classification": "Bug", "reason": "Reports an error"}'
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        
        # Test classification
        result = classify_issue(
            mock_client,
            "App crashes on startup",
            "The application throws an error",
            ['Bug', 'Enhancement', 'Question']
        )
        
        self.assertEqual(result['classification'], 'Bug')
        self.assertIn('error', result['reason'].lower())


class TestCICDAgent(unittest.TestCase):
    """Test CI/CD agent with mocked GitHub API"""
    
    @patch('cicd_agent.requests.get')
    def test_get_workflow_run(self, mock_get):
        """Test fetching workflow run details"""
        from cicd_agent import CICDAgent
        
        # Mock workflow run response
        mock_get.return_value = MockResponse(
            json_data={
                'id': 123,
                'name': 'Tests',
                'conclusion': 'failure',
                'head_sha': 'abc123',
                'pull_requests': [{'number': 42}]
            },
            status_code=200
        )
        
        agent = CICDAgent()
        agent.github_token = 'fake-token'
        agent.repo = 'owner/repo'
        
        run_data = agent.get_workflow_run('123')
        
        self.assertIsNotNone(run_data)
        self.assertEqual(run_data['conclusion'], 'failure')
        self.assertEqual(run_data['pull_requests'][0]['number'], 42)
    
    def test_build_log_analyzer(self):
        """Test build log analysis without external dependencies"""
        from cicd_agent import BuildLogAnalyzer
        
        analyzer = BuildLogAnalyzer()
        
        # Test test failure detection
        logs = """
        Running tests...
        FAIL src/test.js
          ● Test suite failed to run
            Cannot find module 'axios'
        """
        
        analysis = analyzer.analyze(logs)
        
        # Should detect either test_failure or dependency_error
        self.assertIn(analysis['failure_type'], ['test_failure', 'dependency_error'])
        self.assertTrue(len(analysis['suggestions']) > 0)
        self.assertIn(analysis['severity'], ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'])


class TestCommunityAssistant(unittest.TestCase):
    """Test community assistant with mocked components"""
    
    def test_search_codebase(self):
        """Test codebase search functionality"""
        from community_assistant import search_codebase
        
        # Mock indexed files
        indexed_files = {
            'test.py': {
                'content': 'def hello():\n    print("Hello")\n',
                'lines': ['def hello():', '    print("Hello")', ''],
                'size': 100
            }
        }
        
        results = search_codebase(indexed_files, 'hello function', max_results=5)
        
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0]['file'], 'test.py')
    
    def test_generate_permalink(self):
        """Test GitHub permalink generation"""
        from community_assistant import generate_permalink
        
        url = generate_permalink('owner', 'repo', 'main', 'src/test.py', 10, 15)
        
        self.assertIn('github.com', url)
        self.assertIn('owner/repo', url)
        self.assertIn('src/test.py', url)
        self.assertIn('L10-L15', url)
    
    @patch('community_assistant.requests.post')
    @patch('community_assistant.Groq')
    def test_answer_question(self, mock_groq, mock_post):
        """Test question answering with mocked LLM"""
        from community_assistant import answer_question
        
        # Mock Groq response
        mock_client = MagicMock()
        mock_groq.return_value = mock_client
        
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = 'The hello function is defined in test.py'
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        
        indexed_files = {
            'test.py': {
                'content': 'def hello(): pass',
                'lines': ['def hello(): pass'],
                'size': 20
            }
        }
        
        answer = answer_question(
            mock_client,
            'How does hello work?',
            indexed_files,
            'owner',
            'repo',
            'main'
        )
        
        self.assertIsNotNone(answer)
        self.assertIn('hello', answer.lower())


class TestOrchestrator(unittest.TestCase):
    """Test orchestrator functionality"""
    
    def test_event_routing(self):
        """Test event routing logic"""
        from orchestrator import Orchestrator
        
        orch = Orchestrator()
        
        # Test various event types
        self.assertEqual(orch.route_event('pull_request', {}), 'pr_reviewer')
        self.assertEqual(orch.route_event('issues', {}), 'issue_manager')
        self.assertEqual(orch.route_event('workflow_run', {}), 'cicd_agent')
        
        # Test comment routing with @repogent
        event = {'comment': {'body': '@repogent help me'}}
        self.assertEqual(orch.route_event('issue_comment', event), 'community_assistant')
        
        # Test comment routing without @repogent
        event = {'comment': {'body': 'regular comment'}}
        self.assertEqual(orch.route_event('issue_comment', event), 'issue_manager')
    
    def test_message_validation(self):
        """Test message validation and size limits"""
        from orchestrator import Message
        
        # Valid message
        msg = Message('agent1', 'agent2', 'test', {'key': 'value'})
        self.assertIsNotNone(msg.id)
        self.assertEqual(msg.sender, 'agent1')
        
        # Invalid sender type
        with self.assertRaises(ValueError):
            Message(123, 'agent2', 'test', {})
        
        # Invalid payload type
        with self.assertRaises(ValueError):
            Message('agent1', 'agent2', 'test', 'not a dict')
    
    def test_context_path_sanitization(self):
        """Test context store path traversal prevention"""
        from orchestrator import ContextStore
        
        store = ContextStore('.test_context')
        
        # Test sanitization removes dangerous characters
        safe_id = store._sanitize_context_id('../../../etc/passwd')
        self.assertNotIn('..', safe_id)
        self.assertNotIn('/', safe_id)
        
        # Cleanup
        import shutil
        if Path('.test_context').exists():
            shutil.rmtree('.test_context')


class TestConfigConstants(unittest.TestCase):
    """Test shared configuration constants"""
    
    def test_model_selection(self):
        """Test model selection helper"""
        from config_constants import get_model_for_task
        
        # All tasks now use llama-3.3-70b-versatile (3.1-8b-instant decommissioned)
        self.assertEqual(get_model_for_task('pr_review'), 'llama-3.3-70b-versatile')
        self.assertEqual(get_model_for_task('issue_triage'), 'llama-3.3-70b-versatile')
        self.assertEqual(get_model_for_task('community_qa'), 'llama-3.3-70b-versatile')
        self.assertEqual(get_model_for_task('comment_response'), 'llama-3.3-70b-versatile')
    
    def test_truncation_sizes(self):
        """Test log truncation size calculation"""
        from config_constants import get_truncation_sizes, MAX_LOG_SIZE_BYTES
        
        # Small size - no truncation needed
        head, tail = get_truncation_sizes(1000)
        self.assertEqual(head, 1000)
        self.assertEqual(tail, 0)
        
        # Large size - needs truncation
        head, tail = get_truncation_sizes(MAX_LOG_SIZE_BYTES * 2)
        self.assertTrue(head > 0)
        self.assertTrue(tail > 0)
        self.assertTrue(head + tail < MAX_LOG_SIZE_BYTES)


# Run all tests
if __name__ == '__main__':
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test cases
    suite.addTests(loader.loadTestsFromTestCase(TestPostReviewComments))
    suite.addTests(loader.loadTestsFromTestCase(TestTriageIssue))
    suite.addTests(loader.loadTestsFromTestCase(TestCICDAgent))
    suite.addTests(loader.loadTestsFromTestCase(TestCommunityAssistant))
    suite.addTests(loader.loadTestsFromTestCase(TestOrchestrator))
    suite.addTests(loader.loadTestsFromTestCase(TestConfigConstants))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Summary
    print("\n" + "=" * 60)
    if result.wasSuccessful():
        print("✅ ALL INTEGRATION TESTS PASSED!")
        print(f"   Ran {result.testsRun} tests successfully")
    else:
        print("❌ SOME TESTS FAILED")
        print(f"   Failures: {len(result.failures)}")
        print(f"   Errors: {len(result.errors)}")
    print("=" * 60)
    
    sys.exit(0 if result.wasSuccessful() else 1)
