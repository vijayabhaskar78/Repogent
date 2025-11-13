#!/bin/bash
# Repogent Deployment Test Script
# Tests all components of the system

set -e

REPO_URL="https://github.com/vijayabhaskar78/Repogent"
TIMESTAMP=$(date +%s)

echo "🧪 Repogent Deployment Test Script"
echo "=================================="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}📋 Testing Checklist:${NC}"
echo ""

# Test 1: Check if we're in the right directory
echo "1️⃣ Checking repository..."
if [ ! -d ".git" ]; then
    echo -e "${RED}❌ Not in a git repository${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Git repository found${NC}"

# Test 2: Check if scripts exist
echo ""
echo "2️⃣ Checking required files..."
REQUIRED_FILES=(
    "scripts/orchestrator.py"
    "scripts/cicd_agent.py"
    "scripts/review_pr.py"
    "scripts/triage_issue.py"
    "scripts/community_assistant.py"
    "scripts/config_constants.py"
    ".github/workflows/orchestrator.yml"
    ".github/workflows/pr-review.yml"
    ".github/workflows/issue-triage.yml"
    ".github/workflows/cicd-monitor.yml"
    ".github/workflows/community-assistant.yml"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✅${NC} $file"
    else
        echo -e "${RED}❌${NC} $file (missing)"
        exit 1
    fi
done

# Test 3: Run local tests
echo ""
echo "3️⃣ Running local tests..."
python3 test_multi_agent.py > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Multi-agent tests passed${NC}"
else
    echo -e "${RED}❌ Multi-agent tests failed${NC}"
    exit 1
fi

python3 test_integration.py > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Integration tests passed${NC}"
else
    echo -e "${RED}❌ Integration tests failed${NC}"
    exit 1
fi

# Test 4: Check syntax
echo ""
echo "4️⃣ Checking Python syntax..."
python3 -m py_compile scripts/*.py test_*.py > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ All Python files have valid syntax${NC}"
else
    echo -e "${RED}❌ Syntax errors found${NC}"
    exit 1
fi

# Test 5: Check YAML syntax
echo ""
echo "5️⃣ Checking YAML syntax..."
python3 -c "import yaml; import sys; files = ['.github/workflows/orchestrator.yml', '.github/workflows/pr-review.yml', '.github/workflows/issue-triage.yml', '.github/workflows/cicd-monitor.yml', '.github/workflows/community-assistant.yml', 'action.yaml']; [yaml.safe_load(open(f)) for f in files]; sys.exit(0)" 2>/dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ All YAML files are valid${NC}"
else
    echo -e "${RED}❌ YAML syntax errors found${NC}"
    exit 1
fi

echo ""
echo "=================================="
echo -e "${GREEN}✅ All local tests passed!${NC}"
echo "=================================="
echo ""

echo -e "${YELLOW}📝 Next Steps - Manual Testing on GitHub:${NC}"
echo ""
echo "1️⃣ Test PR Review:"
echo "   Create a test branch and open a PR:"
echo "   $ git checkout -b test/pr-review-$TIMESTAMP"
echo "   $ echo '# test' >> README.md"
echo "   $ git add README.md && git commit -m 'test: PR review'"
echo "   $ git push origin HEAD"
echo "   Then: Open PR at $REPO_URL/compare"
echo ""

echo "2️⃣ Test Issue Triage:"
echo "   Create an issue at: $REPO_URL/issues/new"
echo "   Title: 'Test issue - app crashes'"
echo "   Body: 'When I run the app, it throws an error'"
echo ""

echo "3️⃣ Test Community Assistant:"
echo "   Comment on any issue with: '@repogent how does this work?'"
echo ""

echo "4️⃣ Check Workflow Runs:"
echo "   View all workflows at: $REPO_URL/actions"
echo ""

echo "5️⃣ Verify Secrets:"
echo "   Ensure GROQ_API_KEY is set at:"
echo "   $REPO_URL/settings/secrets/actions"
echo ""

echo -e "${GREEN}🎉 Ready for testing!${NC}"
