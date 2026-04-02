#!/usr/bin/env python3
"""Phase 0 data collection script for codebase-explorer skill.

Scans a project directory and produces:
  - terminology.json: BPE-based term extraction
  - structure.json: directory structure with sensitive dir marking
  - hotspots.json: hotspot files by size and naming keywords
  - dependencies.json: dependency list (business vs framework)

Zero external dependencies — uses only Python stdlib.
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

# --- Sensitive directories to skip during scans ---
SKIP_DIRS = {
    "node_modules", ".git", ".svn", ".hg", "__pycache__", ".idea",
    ".vscode", "dist", "build", "target", ".gradle", ".mvn", ".next",
    ".nuxt", ".cache", ".tox", ".eggs", "eggs", "venv", ".venv",
    "env", ".env", ".mypy_cache", ".pytest_cache", ".sass-cache",
    "bower_components", "vendor", "Pods", ".terraform",
}

# --- File extensions to skip for content scanning ---
SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".jar", ".war", ".class", ".pyc", ".pyo", ".so", ".dll", ".dylib",
    ".mp3", ".mp4", ".avi", ".mov", ".wav", ".flv",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".db", ".sqlite", ".bin", ".dat", ".exe", ".o", ".a",
}

# --- Hotspot naming keywords ---
HOTSPOT_KEYWORDS = [
    "Controller", "Service", "Handler", "Manager", "Provider",
    "Repository", "Dao", "Mapper", "Config", "Router",
    "Middleware", "Interceptor", "Filter", "Listener",
    "Scheduler", "Job", "Task", "Worker", "Executor",
    "Factory", "Builder", "Strategy", "Adapter", "Proxy",
    "Entity", "Model", "Dto", "Vo", "Request", "Response",
    "Constants", "Enum", "Exception", "Error",
]

# --- Framework dependencies to exclude from "business deps" ---
FRAMEWORK_PATTERNS = {
    # Java
    "spring-boot", "spring-boot-starter", "spring-web", "spring-webmvc",
    "spring-security", "spring-data", "spring-cloud", "spring-actuator",
    "mybatis", "mybatis-plus", "hibernate", "jpa", "jdbc",
    "tomcat", "undertow", "netty", "jetty",
    "jackson", "gson", "fastjson", "lombok", "slf4j", "logback",
    "junit", "mockito", "testng",
    "maven", "gradle",
    # JavaScript/TypeScript
    "react", "react-dom", "react-router", "next", "nuxt", "vue",
    "angular", "express", "koa", "fastify", "nestjs",
    "webpack", "vite", "rollup", "esbuild", "parcel",
    "babel", "typescript", "eslint", "prettier",
    "jest", "mocha", "vitest", "cypress", "playwright",
    "axios", "lodash", "moment", "dayjs",
    "tailwindcss", "sass", "postcss", "less",
    # Python
    "django", "flask", "fastapi", "tornado", "aiohttp",
    "sqlalchemy", "alembic", "celery", "redis", "rq",
    "pytest", "unittest", "tox", "black", "flake8", "mypy",
    "requests", "httpx", "aiofiles", "pydantic",
    # Go
    "gin", "echo", "fiber", "chi", "mux",
    "gorm", "sqlx", "pgx",
    # Rust
    "actix", "rocket", "axum", "warp", "tokio",
    "serde", "diesel", "sqlx",
    # DevOps/Infra
    "docker", "kubernetes", "k8s",
}

# --- Source file extensions for term extraction ---
SOURCE_EXTENSIONS = {
    ".java", ".kt", ".scala", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".go", ".rs", ".rb", ".php", ".cs", ".swift", ".m",
    ".c", ".cpp", ".h", ".hpp", ".vue", ".svelte",
}


def load_blacklist(skill_dir: str) -> set:
    """Load the terminology blacklist from references/blacklist.txt."""
    blacklist_path = os.path.join(skill_dir, "references", "blacklist.txt")
    blacklist = set()
    if os.path.exists(blacklist_path):
        with open(blacklist_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    blacklist.add(line.lower())
    return blacklist


# ============================================================
# BPE Term Extraction
# ============================================================

def bpe_train(texts: list, num_merges: int = 500) -> list:
    """Simple BPE: learn merge operations from a corpus.

    Returns a list of merge tuples (pair_a, pair_b) in order.
    """
    # Split texts into character-level tokens with word boundaries
    word_freqs: Counter = Counter()
    for text in texts:
        # Split on whitespace and common delimiters
        words = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', text)
        for word in words:
            # Represent as tuple of chars + end marker
            chars = tuple(list(word.lower()) + ["</w>"])
            word_freqs[chars] += 1

    if not word_freqs:
        return []

    merges = []
    for _ in range(min(num_merges, 300)):
        # Count pairs
        pair_counts: Counter = Counter()
        for word, freq in word_freqs.items():
            for i in range(len(word) - 1):
                pair_counts[(word[i], word[i + 1])] += freq

        if not pair_counts:
            break

        # Find best pair
        best_pair = max(pair_counts, key=pair_counts.get)
        if pair_counts[best_pair] < 2:
            break

        merges.append(best_pair)

        # Apply merge
        new_word_freqs: Counter = Counter()
        for word, freq in word_freqs.items():
            new_word = []
            i = 0
            while i < len(word):
                if (i < len(word) - 1 and
                        word[i] == best_pair[0] and
                        word[i + 1] == best_pair[1]):
                    new_word.append(best_pair[0] + best_pair[1])
                    i += 2
                else:
                    new_word.append(word[i])
                    i += 1
            new_word_freqs[tuple(new_word)] += freq
        word_freqs = new_word_freqs

    return merges


def bpe_tokenize(word: str, merges: list) -> list:
    """Apply BPE merges to a single word."""
    tokens = list(word.lower()) + ["</w>"]
    for pair_a, pair_b in merges:
        new_tokens = []
        i = 0
        while i < len(tokens):
            if (i < len(tokens) - 1 and
                    tokens[i] == pair_a and
                    tokens[i + 1] == pair_b):
                new_tokens.append(pair_a + pair_b)
                i += 2
            else:
                new_tokens.append(tokens[i])
                i += 1
        tokens = new_tokens
    # Remove </w> marker
    tokens = [t.replace("</w>", "") for t in tokens if t != "</w>"]
    return [t for t in tokens if t]


def extract_terms(project_root: str, blacklist: set) -> dict:
    """Extract terminology using BPE from source files."""
    # Collect text from source files (limit total to avoid memory issues)
    texts = []
    total_chars = 0
    max_chars = 2_000_000  # ~2MB of source text

    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext in SOURCE_EXTENSIONS:
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        texts.append(content)
                        total_chars += len(content)
                        if total_chars >= max_chars:
                            break
                except (OSError, IOError):
                    continue
        if total_chars >= max_chars:
            break

    if not texts:
        return {"terms": [], "method": "bpe", "note": "no source files found"}

    # Train BPE
    merges = bpe_train(texts, num_merges=300)

    # Extract terms from all texts
    term_counter: Counter = Counter()
    for text in texts:
        words = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]{2,}', text)
        for word in words:
            tokens = bpe_tokenize(word, merges)
            for token in tokens:
                # Filter short BPE fragments (< 3 chars are usually noise)
                if len(token) < 3:
                    continue
                if token.lower() in blacklist:
                    continue
                term_counter[token.lower()] += 1

    # Filter: remove single chars and low frequency
    total_words = sum(term_counter.values()) or 1
    terms = []
    for term, count in term_counter.most_common(200):
        if count < 3:
            continue
        # Skip pure numbers
        if term.isdigit():
            continue
        terms.append({
            "term": term,
            "frequency": count,
            "ratio": round(count / total_words, 6),
        })

    return {
        "terms": terms[:100],  # Top 100 terms
        "method": "bpe",
        "source_file_count": len(texts),
        "total_chars_scanned": total_chars,
    }


# ============================================================
# Structure Analysis
# ============================================================

def scan_structure(project_root: str, max_depth: int = 5) -> dict:
    """Scan directory structure with sensitive dir marking."""
    structure = {
        "root": os.path.basename(project_root),
        "tree": {},
        "sensitive_dirs": [],
        "source_dirs": [],
        "top_level": [],
    }

    # Get top-level entries
    try:
        entries = sorted(os.listdir(project_root))
    except OSError:
        return structure

    for entry in entries:
        full = os.path.join(project_root, entry)
        if os.path.isdir(full):
            structure["top_level"].append({"name": entry, "type": "dir"})
        else:
            structure["top_level"].append({"name": entry, "type": "file"})

    # Build tree recursively
    def _scan(path: str, depth: int) -> dict:
        if depth > max_depth:
            return {"_truncated": True}

        result = {}
        try:
            entries = sorted(os.listdir(path))
        except OSError:
            return result

        # Limit entries per level
        for entry in entries[:100]:
            if entry.startswith(".") and entry not in {".github", ".gitlab", ".env.example"}:
                continue
            full = os.path.join(path, entry)
            rel = os.path.relpath(full, project_root)

            if os.path.isdir(full):
                if entry in SKIP_DIRS:
                    structure["sensitive_dirs"].append(rel)
                    continue

                has_source = False
                # Check if dir contains source files
                for sub_root, sub_dirs, sub_files in os.walk(full):
                    sub_dirs[:] = [d for d in sub_dirs if d not in SKIP_DIRS]
                    for sf in sub_files:
                        if os.path.splitext(sf)[1].lower() in SOURCE_EXTENSIONS:
                            has_source = True
                            break
                    if has_source:
                        break

                if has_source:
                    structure["source_dirs"].append(rel)

                result[entry + "/"] = _scan(full, depth + 1)
            else:
                ext = os.path.splitext(entry)[1].lower()
                size = 0
                try:
                    size = os.path.getsize(full)
                except OSError:
                    pass
                result[entry] = {"_size": size, "_ext": ext}

        return result

    structure["tree"] = _scan(project_root, 0)
    return structure


# ============================================================
# Hotspot Detection
# ============================================================

def find_hotspots(project_root: str, top_n: int = 50) -> dict:
    """Find hotspot files by size and naming keywords."""
    file_info = []

    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext in SKIP_EXTENSIONS:
                continue
            fpath = os.path.join(root, fname)
            try:
                size = os.path.getsize(fpath)
            except OSError:
                continue

            rel = os.path.relpath(fpath, project_root)

            # Score based on keywords
            keyword_hits = []
            name_part = os.path.splitext(fname)[0]
            for kw in HOTSPOT_KEYWORDS:
                if kw.lower() in name_part.lower():
                    keyword_hits.append(kw)

            file_info.append({
                "path": rel,
                "size": size,
                "ext": ext,
                "keywords": keyword_hits,
                "score": len(keyword_hits) * 100 + min(size / 100, 100),
            })

    # Sort by score descending
    file_info.sort(key=lambda x: x["score"], reverse=True)

    # Categorize
    by_keyword = {}
    for f in file_info:
        for kw in f["keywords"]:
            if kw not in by_keyword:
                by_keyword[kw] = []
            if len(by_keyword[kw]) < 10:
                by_keyword[kw].append(f["path"])

    return {
        "top_by_score": [
            {"path": f["path"], "size": f["size"], "keywords": f["keywords"]}
            for f in file_info[:top_n]
        ],
        "by_keyword": by_keyword,
        "keyword_counts": {kw: len(paths) for kw, paths in by_keyword.items()},
        "total_source_files": len(file_info),
    }


# ============================================================
# Dependency Analysis
# ============================================================

def analyze_dependencies(project_root: str) -> dict:
    """Analyze project dependencies, categorizing as business or framework."""

    deps = {
        "business": [],
        "framework": [],
        "tools": [],
        "source": None,
    }

    # Try different dependency files
    dep_files = [
        ("package.json", _parse_package_json),
        ("pom.xml", _parse_pom_xml),
        ("build.gradle", _parse_gradle),
        ("requirements.txt", _parse_requirements),
        ("go.mod", _parse_go_mod),
        ("Cargo.toml", _parse_cargo),
    ]

    for fname, parser in dep_files:
        fpath = os.path.join(project_root, fname)
        if os.path.exists(fpath):
            deps["source"] = fname
            result = parser(fpath)
            for dep_name in result:
                dep_lower = dep_name.lower()
                categorized = False
                for fp in FRAMEWORK_PATTERNS:
                    if fp in dep_lower:
                        deps["framework"].append(dep_name)
                        categorized = True
                        break
                if not categorized:
                    deps["business"].append(dep_name)
            break

    # Remove duplicates while preserving order
    for key in ["business", "framework", "tools"]:
        seen = set()
        unique = []
        for item in deps[key]:
            if item not in seen:
                seen.add(item)
                unique.append(item)
        deps[key] = unique

    return deps


def _parse_package_json(fpath: str) -> list:
    """Parse dependencies from package.json."""
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
        deps = list(data.get("dependencies", {}).keys())
        dev_deps = list(data.get("devDependencies", {}).keys())
        return deps + dev_deps
    except (json.JSONDecodeError, OSError):
        return []


def _parse_pom_xml(fpath: str) -> list:
    """Parse dependencies from pom.xml (simple regex)."""
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
        # Extract artifactIds inside <dependency> blocks
        deps = re.findall(
            r'<dependency>.*?<artifactId>([^<]+)</artifactId>.*?</dependency>',
            content, re.DOTALL
        )
        return deps
    except OSError:
        return []


def _parse_gradle(fpath: str) -> list:
    """Parse dependencies from build.gradle (simple regex)."""
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
        # Match implementation 'group:artifact:version' or implementation("...")
        deps = re.findall(
            r"(?:implementation|api|compileOnly|runtimeOnly)['\"]([^'\"]+)['\"]",
            content
        )
        # Also match group:artifact:version format → extract artifact
        result = []
        for dep in deps:
            parts = dep.split(":")
            if len(parts) >= 2:
                result.append(parts[1])
            else:
                result.append(dep)
        return result
    except OSError:
        return []


def _parse_requirements(fpath: str) -> list:
    """Parse dependencies from requirements.txt."""
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        deps = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("-"):
                # Extract package name (before ==, >=, etc.)
                match = re.match(r'^([a-zA-Z0-9_-]+)', line)
                if match:
                    deps.append(match.group(1))
        return deps
    except OSError:
        return []


def _parse_go_mod(fpath: str) -> list:
    """Parse dependencies from go.mod."""
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
        # Match require blocks
        deps = re.findall(r'^\s*([a-zA-Z0-9./_-]+)\s+v[\d.]+', content, re.MULTILINE)
        return [d.split("/")[-1] if "/" in d else d for d in deps]
    except OSError:
        return []


def _parse_cargo(fpath: str) -> list:
    """Parse dependencies from Cargo.toml."""
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
        # Simple regex for [dependencies] section
        in_deps = False
        deps = []
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped == "[dependencies]":
                in_deps = True
                continue
            if stripped.startswith("[") and in_deps:
                break
            if in_deps and "=" in stripped:
                name = stripped.split("=")[0].strip()
                deps.append(name)
        return deps
    except OSError:
        return []


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Phase 0 data collection for codebase-explorer"
    )
    parser.add_argument(
        "--project-root", required=True,
        help="Root directory of the project to scan"
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Output directory (default: <project-root>/.claude/p0-data)"
    )
    parser.add_argument(
        "--skill-dir", default=None,
        help="Path to the codebase-explorer skill directory (for blacklist)"
    )
    args = parser.parse_args()

    project_root = os.path.abspath(args.project_root)
    if not os.path.isdir(project_root):
        print(f"Error: {project_root} is not a directory", file=sys.stderr)
        sys.exit(1)

    output_dir = args.output_dir or os.path.join(project_root, ".claude", "p0-data")
    os.makedirs(output_dir, exist_ok=True)

    # Determine skill dir (for blacklist)
    skill_dir = args.skill_dir
    if not skill_dir:
        # Assume this script is in <skill>/scripts/
        skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    print(f"Scanning project: {project_root}")
    print(f"Output directory: {output_dir}")

    # Load blacklist
    blacklist = load_blacklist(skill_dir)
    print(f"Blacklist loaded: {len(blacklist)} terms")

    # Run scans
    print("\n[1/4] Extracting terminology...")
    terminology = extract_terms(project_root, blacklist)
    _save(output_dir, "terminology.json", terminology)
    print(f"  → {len(terminology['terms'])} terms extracted")

    print("[2/4] Scanning structure...")
    structure = scan_structure(project_root)
    _save(output_dir, "structure.json", structure)
    print(f"  → {len(structure['source_dirs'])} source dirs, {len(structure['sensitive_dirs'])} sensitive dirs")

    print("[3/4] Finding hotspots...")
    hotspots = find_hotspots(project_root)
    _save(output_dir, "hotspots.json", hotspots)
    print(f"  → {hotspots['total_source_files']} source files, {len(hotspots['keyword_counts'])} keyword categories")

    print("[4/4] Analyzing dependencies...")
    dependencies = analyze_dependencies(project_root)
    _save(output_dir, "dependencies.json", dependencies)
    print(f"  → {len(dependencies['business'])} business deps, {len(dependencies['framework'])} framework deps")
    if dependencies["source"]:
        print(f"  → Source: {dependencies['source']}")

    print(f"\nDone. Output saved to {output_dir}/")


def _save(output_dir: str, filename: str, data: dict):
    """Save data as JSON."""
    fpath = os.path.join(output_dir, filename)
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
