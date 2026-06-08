# Project Health Audit Workflow

A systematic way to proactively scan a multi-module Python project for ALL possible issues — without a specific bug report. Use this before releasing changes, after merging large PRs, or when asked "what needs fixing."

## When to Use

- User asks "看看还有什么需要完善的" (check what needs improvement)
- Before deploying a framework change
- After merging a large feature branch
- Periodic maintenance scans

## The 7-Dimension Audit Checklist

### 1️⃣ Syntax Check (fast, always first)

```python
import ast, glob

for f in sorted(glob.glob(f"{project_dir}/**/*.py", recursive=True)):
    try:
        with open(f) as fh:
            ast.parse(fh.read())
    except SyntaxError as e:
        print(f"❌ {f}: {e}")
```

### 2️⃣ Import Chain Verification

For projects with a known dependency graph (e.g., a layered framework):

```bash
# Test each layer in order
python3 -c "from layer1.module1 import ...; print('layer1 OK')"
python3 -c "from layer2.module2 import ...; print('layer2 OK')"
```

**Pattern for dataflow projects**: trace imports from leaf algorithms → intermediate wrappers → top-level entry points → agents → graph compilation.

**Key questions**:
- Can each file import in isolation (not namespace-package reliant)?
- Are circular imports present?
- Are there `__init__.py` exports that don't match the actual public API?

### 3️⃣ Edge Case Coverage

For code that processes real-world data (K-lines, sensor readings, user input):

| Edge Case | What to Test |
|-----------|-------------|
| **Empty input** | Empty list, None, 0 rows |
| **Minimum viable** | Minimum required length (e.g., 7 K-lines for 缠论) |
| **Near-boundary** | Exactly the minimum, minimum+1 |
| **Monotonic input** | All-up, all-down — no alternation |
| **Noisy input** | Redundant patterns, data that triggers all filters |
| **Pathological** | Data that triggers recursion, long loops, edge branches |

### 4️⃣ Data Flow Completeness

For layered systems where data flows module A → B → C → D:

```python
# Mock the output of each layer and verify the next layer accepts it
mock_output_A = {...}
result_B = module_B.process(mock_output_A)
result_C = module_C.process(result_B)
```

**Key questions**:
- Does each layer's output match what the next layer expects?
- Are there type mismatches at layer boundaries?
- Are missing fields silently ignored or causing crashes?

### 5️⃣ Graph/Workflow Compilation

For LangGraph, LangChain, or similar pipeline frameworks:

```python
# Test graph compilation without invoking LLM calls
from my_package.graph import MyGraph
g = MyGraph()
assert len(g.graph.nodes) > 0, "Graph compiled to empty!"
print(f"✅ Graph compiled: {len(g.graph.nodes)} nodes, {len(g.graph.edges)} edges")
```

**Key signals**:
- Compilation succeeds → routing is correct
- Expected number of nodes present → no missing components
- Can inspect node names to verify ordering

### 6️⃣ Dependency Completeness

```bash
# Check what's actually installed vs. what's declared
pip list --format=columns | grep -i <package>
```

**For projects without lockfiles**: manually test imports of all declared dependencies:

```python
# Run in venv
for pkg in ["langchain-core", "langchain-openai", "langgraph", "pandas", "mootdx"]:
    try:
        __import__(pkg)
        print(f"✅ {pkg}")
    except ImportError:
        print(f"❌ {pkg}")
```

**Categorize missing deps**:
- **Core** (blocks main path) → must install
- **Optional** (alternate data sources, alternative backends, Web UI) → document fallback behavior
- **Unused** (declared but not imported anywhere) → consider removing from pyproject.toml

### 7️⃣ Documentation Sync

Check that documentation (README, skill files, inline comments) matches reality:

| What Could Be Out of Sync | How to Check |
|--------------------------|-------------|
| Entry point commands | Test `python -m module`, `cli/main.py`, declared `[project.scripts]` |
| API signatures | Grep for `def function_name` vs. how it's called |
| Dependency list | Compare pyproject.toml vs. actual imports |
| Architecture diagrams | Trace each box → does it have a real file? |
| Fallback behavior docs | Intentionally trigger each fallback |

## The Scoring Framework

After audit, score each dimension and prioritize:

| Score | Meaning | Action |
|-------|---------|--------|
| ✅ Green | Working correctly | Document |
| ⚠️ Yellow | Works but suboptimal | P1 (improve within session) |
| 🔴 Red | Bug or missing feature | P0 (fix immediately) |
| 🔵 Blue | Enhancement opportunity | P2 (nice to have) |

## Hermes-Specific Tips

- Use `delegate_task` with toolsets=['terminal','file'] to parallelize the audit across independent modules
- Scan 100+ file projects efficiently by focusing on `from X import Y` import chains rather than reading every file
- For LangGraph projects: always attempt graph compilation — it's the fastest way to validate routing correctness
- When API keys cause test failures but code logic is correct, note the distinction: "graph compiled OK, LLM failed due to auth" = code is fine, environment is the issue
