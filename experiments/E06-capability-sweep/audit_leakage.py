"""E06 leakage audit of the LLM arms (hybrid, model-only), their drivers and the phase-1 harness agents.

Run from pipeline/ with its venv (the sdp-guard check imports chinese_workflow and the guard test):

    cd pipeline && E06_SESSION_DIR=<claude-session-dir> E06_SCRATCHPAD_DIR=<scratchpad> \
        .venv/bin/python ../experiments/E06-capability-sweep/audit_leakage.py

It needs the original Claude Code transcripts of the E06 session, which are not part of this
repository. E06_SESSION_DIR is that session's transcript directory
(~/.claude/projects/<project>/55959ab8-efb9-460b-b410-9170201713a7) and E06_SCRATCHPAD_DIR its scratchpad. In the
committed leakage-audit.json these are written <claude-session-dir> and <scratchpad>, the checkout the
session worked in <repo>, and the home directory <home>. Transcript paths are classified against this
checkout's location, so run the audit from a checkout at the path the session used. The script writes
the real paths; replace them with these placeholders before committing a re-run's leakage-audit.json.

What it does (paths and counts only; it never prints or writes source text, gold text or sdp headings):
  1. Parses every agent transcript of the E06 answer workflow (journal labels 'answer:r<round>:<cell>:<task>:
     <hash8>', 'drive:r<n>', 'finalize-score') and of the phase-1 build workflow, and extracts every tool_use:
     Read/Write/Edit file_path, Grep/Glob path+pattern, Bash path-like tokens, web tools, sub-agents.
  2. Classifies each answer agent's accesses: ALLOWED (own request .md/.json, own response, the pipeline
     interpreter of the validation one-liner), SUSPECT (anything else), FORBIDDEN (golds, raw sdp / YBh /
     CBETA corpus, tests/, context/, skills/, docs/, another hash's request/response, runs/*/outline*,
     metrics/score files, any web tool).
  3. Drivers / finalize: may run the harness; FORBIDDEN = opening a gold, raw eval data, tests/fixtures,
     context/research or a "Do not open while developing" file by hand. Phase-1 agents: FORBIDDEN = a
     "Do not open" file; programmatic gold access is listed as a note.
  4. For every agent: T34n1718 / T34n1723 lineheads of the test or reserve split in tool results and tool
     inputs, with or without following text, excluding lineheads that committed docs / harness code already
     state (split boundaries etc.).
  5. Answer agents: gold-only marker strings in tool results that their own request does not contain; sdp
     headings (>= 5 chars) in their response that their own request does not contain (count + digest).
  6. Request files: T34n1718 / T34n1723 text lines per split in every runs/*/llm/requests/*.md.
  7. E06 output files: the check of tests/unit/test_sdp_eval_only_guard.py (imported), applied to E06's
     untracked outputs as if they were tracked; plus test/reserve lineheads not stated in committed docs.
  8. DEV ONLY (Kuiji 陀羅尼品 subtree): which gold nodes the two independent answers to the root-spans request
     626ce7f0 filled, by the gold's root_text.basis, and how many starts/ends they share with it (counts).
Writes experiments/E06-capability-sweep/leakage-audit.json.
"""

from __future__ import annotations

import fnmatch
import glob
import hashlib
import importlib.util
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
E06 = REPO / "experiments" / "E06-capability-sweep"
PIPE = REPO / "pipeline"
SESSION_ENV, SCRATCHPAD_ENV = "E06_SESSION_DIR", "E06_SCRATCHPAD_DIR"  # see the module docstring
SESSION = Path(os.environ.get(SESSION_ENV) or "<claude-session-dir>")
WF_ANSWER = SESSION / "subagents" / "workflows" / "wf_f7cda63c-444"
WF_PHASE1 = SESSION / "subagents" / "workflows" / "wf_f3748cc6-66d"
OUT = E06 / "leakage-audit.json"

sys.path.insert(0, str(PIPE / "src"))
from chinese_workflow.common.splits import load_registry, split_of_line  # noqa: E402

REG = load_registry()

SEV = {"NEUTRAL": 0, "ALLOWED": 1, "NOTE": 2, "SUSPECT": 3, "FORBIDDEN": 4}
HEX64 = re.compile(r"[0-9a-f]{64}")
LABEL_RE = re.compile(r"^answer:r(\d+):([^:]+):([^:]+):([0-9a-f]{8})$")
CJK = re.compile(r"[㐀-鿿豈-﫿\U00020000-\U0002ffff]")
LH_RE = re.compile(r"(T34n17(?:18|23))_p(\d{4}[abc]\d{2})")
LB_RE = re.compile(r"<lb\b[^>]*\bn=\"(\d{4}[abc]\d{2})\"")
TOKEN_SPLIT = re.compile(r"[\s'\"`(){}\[\],;|&<>=]+")
PATHLIKE = re.compile(r"^[~.\w@+\-/*?]+$")
KNOWN_TOP = {"data", "tests", "context", "skills", "docs", "experiments", "pipeline", "scripts", "projects",
             "runs", "llm", "src", "schemas", ".venv", "~", ".", ".."}
EXTS = (".json", ".jsonl", ".md", ".txt", ".xml", ".py", ".tsv", ".toml", ".csv", ".docx", ".html")
WEB_TOOLS = {"WebFetch", "WebSearch"}
WEB_CMD = re.compile(r"\b(curl|wget|lynx)\b|urllib\.request|requests\.(get|post)\(|httpx\.")
SEARCH_CMD = re.compile(r"(^|[\s;&|])(grep|rg|ag|find|ls|tree|locate)\b")

# The "Do not open while developing" list of data/EVAL-SETS.md (repo-relative prefixes / substrings).
DO_NOT_OPEN = (
    "data/reference-outlines/T0262/kuiji-xuanzan/outline.txt",
    "data/reference-outlines/T0262/kuiji-xuanzan/outline.json",
    "data/reference-outlines/T0262/kuiji-xuanzan/PROVENANCE.md",
    "tests/unit/test_gold_kuiji_testsplit.py",
    "tests/fixtures/R03-piyu-opening",
    "context/research/R03-kuiji-fahua-xuanzan-and-tibetan-parallel/findings.md",
)
DO_NOT_OPEN_SUBSTR = ("kuiji_testsplit", "R03-piyu-opening", "kuiji-xuanzan/outline",
                      "kuiji-xuanzan/PROVENANCE", "R03-kuiji-fahua-xuanzan-and-tibetan-parallel/findings")
GOLD_PREFIXES = ("data/reference-outlines", "data/raw/dila-sdp", "data/raw/dila-ybh")
CORPUS_PREFIXES = ("data/raw/cbeta",)
FORBIDDEN_TOP = ("tests/", "context/", "skills/", "docs/")
METRIC_NAMES = ("metrics*.json", "score*.json", "SUMMARY.md", "looks*.json", "sanity*.json", "projects*.json",
                "leakage-audit.json")
# Strings that occur in gold files / gold metadata but not in pipeline requests by construction.
GOLD_MARKERS = ("reference-outlines", "dila-sdp", "dila-ybh", "zhiyi-wenju-sdp", "draft-unreviewed",
                "imported-unchecked", "seeded_by", "gold_status", "TEST SPLIT", "coverage_spans",
                "cbeta-mulu-kepan", "ybh-dila", "heading-check", "T1718D", "T0262D", "fetch_error",
                "anchor_inherited", "split_notes")


def digest(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def rel(p: str) -> str | None:
    try:
        return Path(p).resolve().relative_to(REPO).as_posix()
    except (ValueError, OSError):
        return None


# ------------------------------------------------------------------------------------------ transcripts


def journal_labels(wf: Path) -> dict:
    labels = {}
    for line in (wf / "journal.jsonl").read_text(encoding="utf-8").splitlines():
        j = json.loads(line)
        if j.get("type") == "started":
            labels[j["agentId"]] = {"label": j.get("label"), "phase": j.get("phase")}
    return labels


def _result_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    return json.dumps(content, ensure_ascii=False) if content is not None else ""


def parse_transcript(path: Path) -> dict:
    prompt, cwd, uses, results, attachments = None, None, [], {}, Counter()
    edited = []
    for line in path.read_text(encoding="utf-8").splitlines():
        j = json.loads(line)
        cwd = cwd or j.get("cwd")
        if j.get("type") == "attachment":
            a = j.get("attachment") or {}
            attachments[a.get("type")] += 1
            if a.get("type") == "edited_text_file":
                edited.append({"path": a.get("filename"), "snippet_chars": len(a.get("snippet") or "")})
            continue
        msg = j.get("message") or {}
        c = msg.get("content")
        if j.get("type") == "user" and isinstance(c, str) and prompt is None:
            prompt = c
            continue
        if not isinstance(c, list):
            continue
        for b in c:
            if b.get("type") == "tool_use":
                uses.append({"id": b["id"], "name": b["name"], "input": b.get("input") or {}})
            elif b.get("type") == "tool_result":
                results[b.get("tool_use_id")] = _result_text(b.get("content"))
    return {"prompt": prompt or "", "cwd": cwd, "uses": uses, "results": results,
            "attachments": dict(attachments), "edited_text_file": edited}


# ------------------------------------------------------------------------------------------ paths


def bash_paths(cmd: str, cwd: str | None) -> list:
    """Path-like tokens of a shell command, resolved (cd-aware); [(token, absolute_or_None)]."""
    out, cd = [], None
    m = re.findall(r"(?:^|[;&|]\s*|\n)\s*cd\s+([^\s;&|]+)", cmd)
    if m:
        cd = m[0]
    base = cd if cd and cd.startswith("/") else (os.path.join(cwd or str(REPO), cd) if cd else (cwd or str(REPO)))
    seen = set()
    for tok in TOKEN_SPLIT.split(cmd):
        tok = tok.strip()
        if not tok or tok in seen or not PATHLIKE.match(tok) or tok in (".", "..", "/", "~"):
            continue
        if tok.startswith("-"):
            continue
        first = tok.split("/", 1)[0]
        has_slash = "/" in tok
        if not (tok.startswith(("/", "./", "../", "~/")) or (has_slash and first in KNOWN_TOP)
                or tok.endswith(EXTS)):
            if not has_slash:
                continue
            cand = os.path.normpath(os.path.join(base, tok))
            if not glob.glob(cand):
                continue  # e.g. a division in inline code, not a path
        seen.add(tok)
        absp = os.path.expanduser(tok) if tok.startswith("~") else tok
        if not absp.startswith("/"):
            absp = os.path.normpath(os.path.join(base, absp))
        out.append((tok, absp))
    return out


def use_paths(use: dict, cwd: str | None) -> list:
    i, name = use["input"], use["name"]
    if name in ("Read", "Write", "Edit", "NotebookEdit"):
        return [(i.get("file_path") or i.get("notebook_path") or "", i.get("file_path") or "")]
    if name in ("Grep", "Glob"):
        p = i.get("path") or cwd or ""
        pats = [(p, p)]
        if i.get("glob"):
            pats.append((i["glob"], os.path.join(p, i["glob"])))
        if name == "Glob" and i.get("pattern"):
            pats.append((i["pattern"], os.path.join(p, i["pattern"])))
        return pats
    if name == "Bash":
        return bash_paths(i.get("command") or "", cwd)
    return []


def _metricish(r: str) -> bool:
    base = r.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(base, pat) for pat in METRIC_NAMES)


HARMLESS = {"/dev/null": "null device", "/usr/bin/python3": "system interpreter", str(REPO): "working directory (cd)",
            str(PIPE): "working directory (cd)", str(E06): "working directory (cd)"}
# the session's scratch root: the directory that holds its scratchpad
SCRATCH = os.path.dirname(os.path.normpath(os.environ.get(SCRATCHPAD_ENV) or "<scratch-root>/scratchpad"))


def classify_answer_path(absp: str, own: dict) -> tuple:
    if not absp:
        return "SUSPECT", "empty path"
    norm = os.path.normpath(absp)
    if norm in HARMLESS and norm != str(E06):
        return "ALLOWED", HARMLESS[norm]
    own_llm = os.path.dirname(os.path.dirname(own["response"]))
    if norm in (own_llm, os.path.dirname(own["response"])):
        return "SUSPECT", "own cell's llm/responses dir (mkdir / ls: file names only)"
    if norm.startswith(SCRATCH):
        return "SUSPECT", "session scratchpad file"
    if os.path.dirname(norm) == os.path.dirname(own["response"]) and norm.endswith("*") \
            and own["_hash"].startswith(os.path.basename(norm).rstrip("*")):
        return "ALLOWED", "own response (glob on own hash)"
    if norm in own.values():
        return "ALLOWED", "own " + [k for k, v in own.items() if v == norm][0]
    if norm in (str(PIPE), str(PIPE / ".venv" / "bin" / "python")) or norm.endswith("/.venv/bin/python"):
        return "ALLOWED", "pipeline interpreter (validation one-liner)"
    r = rel(norm) if "*" not in norm and "?" not in norm else (
        os.path.relpath(norm, REPO) if norm.startswith(str(REPO)) else None)
    if r is None or r.startswith(".."):
        if norm.startswith(str(SESSION / "tool-results")):
            return "SUSPECT", "tool-output overflow file"
        if norm.startswith(("/tmp", "/private/tmp", "/var/folders")):
            return "SUSPECT", "temp file outside repo"
        return "SUSPECT", "outside repo"
    if any(r.startswith(p) for p in DO_NOT_OPEN):
        return "FORBIDDEN", "Do-not-open file"
    if r.startswith(GOLD_PREFIXES):
        return "FORBIDDEN", "gold / eval-only raw data"
    if r.startswith(CORPUS_PREFIXES):
        return "FORBIDDEN", "corpus lookup (data/raw/cbeta)"
    if r.startswith(FORBIDDEN_TOP):
        return "FORBIDDEN", r.split("/", 1)[0] + "/"
    if re.match(r"experiments/[^/]+/runs/[^/]+/outline", r):
        return "FORBIDDEN", "pipeline outline of a cell"
    m = re.search(r"llm/(requests|responses)/([0-9a-f]{64}|[*?][^/]*)", r)
    if m:
        h = m.group(2)
        if HEX64.fullmatch(h) and h == own["_hash"]:
            return "SUSPECT", "same hash in another cell"
        return "FORBIDDEN", "another hash's request/response"
    if _metricish(r):
        return "FORBIDDEN", "metrics/score file"
    if r in ("data/eval-sets.json", "data/EVAL-SETS.md"):
        return "SUSPECT", "eval registry / guide"
    return "SUSPECT", "other repo path"


DRIVER_OK = ("experiments/E06-capability-sweep/run_e06.py", "experiments/E06-capability-sweep/SUMMARY.md",
             "experiments/E06-capability-sweep/metrics.json", "experiments/E06-capability-sweep/looks-e06.json",
             "experiments/E01-explicit-recovery/looks.json", "experiments/E06-capability-sweep/runs",
             "experiments/E06-capability-sweep", "pipeline")


def classify_driver_path(absp: str) -> tuple:
    norm = os.path.normpath(absp)
    if norm in HARMLESS:
        return "ALLOWED", HARMLESS[norm]
    if norm.startswith(SCRATCH):
        return "ALLOWED", "harness output saved in session scratchpad"
    if norm.endswith("/.venv/bin/python") or norm in (str(PIPE),):
        return "ALLOWED", "pipeline interpreter"
    r = rel(norm) if "*" not in norm else (os.path.relpath(norm, REPO) if norm.startswith(str(REPO)) else None)
    if r is None or r.startswith(".."):
        if norm.startswith(str(SESSION / "tool-results")):
            return "ALLOWED", "tool-output overflow file"
        return "SUSPECT", "outside repo"
    if any(r.startswith(p) for p in DO_NOT_OPEN):
        return "FORBIDDEN", "Do-not-open file"
    if r.startswith(GOLD_PREFIXES):
        return "FORBIDDEN", "gold opened by hand"
    if r.startswith(("tests/fixtures", "context/research")):
        return "FORBIDDEN", "fixture / research file"
    if re.search(r"/runs/[^/]+/score-", r):
        return "SUSPECT", "per-cell score file"
    if re.search(r"llm/(requests|responses)/", r) and not r.endswith(".jsonl"):
        return "SUSPECT", "request/response file"
    if r.endswith("llm/invalid.jsonl") or r in DRIVER_OK or any(r.startswith(p + "/") for p in DRIVER_OK[:5]):
        return "ALLOWED", "harness / its outputs"
    if r.startswith(("experiments/E06-capability-sweep/runs/", "experiments/E06-capability-sweep/")):
        return "ALLOWED", "E06 harness tree"
    return "SUSPECT", "other repo path"


def classify_phase1_path(absp: str) -> tuple:
    norm = os.path.normpath(absp)
    r = rel(norm) if "*" not in norm else (os.path.relpath(norm, REPO) if norm.startswith(str(REPO)) else None)
    if r is None or r.startswith(".."):
        return "ALLOWED", "outside repo"
    if any(r.startswith(p) for p in DO_NOT_OPEN):
        return "FORBIDDEN", "Do-not-open file"
    if r.startswith(GOLD_PREFIXES):
        return "NOTE", "gold path (harness development)"
    return "ALLOWED", "repo path"


# ------------------------------------------------------------------------------------------ split scan


def documented_lineheads() -> set:
    """Lineheads committed docs / harness code state (split boundaries, known pairs): not exposures."""
    files = [REPO / "data" / "EVAL-SETS.md", REPO / "data" / "eval-sets.json"]  # committed files only
    files += sorted((PIPE / "src").rglob("*.py"))
    e01 = REPO / "experiments" / "E01-explicit-recovery"
    files += [p for p in e01.iterdir() if p.is_file() and p.suffix in (".py", ".md", ".json")]
    files += sorted((REPO / "docs").rglob("*.md"))
    out = set()
    for p in files:
        if any(rel(str(p)) and rel(str(p)).startswith(d) for d in DO_NOT_OPEN):
            continue
        try:
            out.update("%s_p%s" % m for m in LH_RE.findall(p.read_text(encoding="utf-8")))
        except (UnicodeDecodeError, OSError):
            pass
    return out


DOC_LH = documented_lineheads()


def split_scan(text: str, file_hint: str | None = None) -> Counter:
    """Counts of T34n1718 / T34n1723 test / reserve lineheads: key (file, split, with_text, documented)."""
    c = Counter()
    for m in LH_RE.finditer(text):
        lh = "%s_p%s" % (m.group(1), m.group(2))
        sp = split_of_line(REG, lh)
        if sp not in ("test", "reserve"):
            continue
        tail = text[m.end(): m.end() + 60].split("\n", 1)[0]
        with_text = len(CJK.findall(tail)) >= 4
        c[(m.group(1), sp, with_text, lh in DOC_LH)] += 1
    if file_hint:
        for m in LB_RE.finditer(text):
            lh = "%s_p%s" % (file_hint, m.group(1))
            sp = split_of_line(REG, lh)
            if sp in ("test", "reserve"):
                tail = text[m.end(): m.end() + 60]
                c[(file_hint, sp, len(CJK.findall(tail)) >= 4, lh in DOC_LH)] += 1
    return c


def _hint(use: dict) -> str | None:
    s = json.dumps(use["input"], ensure_ascii=False)
    if "1718" in s:
        return "T34n1718"
    if "1723" in s:
        return "T34n1723"
    return None


def summarize_split(c: Counter) -> dict:
    out = defaultdict(int)
    for (f, sp, wt, doc), n in c.items():
        out["%s:%s:%s%s" % (f, sp, "text" if wt else "locator", ":documented" if doc else "")] += n
    return dict(sorted(out.items()))


def undocumented_text(c: Counter) -> int:
    return sum(n for (f, sp, wt, doc), n in c.items() if wt and not doc)


def undocumented_test_text(c: Counter) -> int:
    return sum(n for (f, sp, wt, doc), n in c.items() if wt and not doc and sp == "test")


# ------------------------------------------------------------------------------------------ sdp headings


def load_guard():
    spec = importlib.util.spec_from_file_location(
        "sdp_guard", REPO / "tests" / "unit" / "test_sdp_eval_only_guard.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


GUARD = load_guard()
SDP_HEADS = GUARD._sdp_headings() if all(p.exists() for p in GUARD.SDP_GOLDS) else set()
SDP_LONG = {h for h in SDP_HEADS if len(h) >= GUARD.LONG}


def sdp_hits(text: str, heads: set) -> set:
    return {h for h in heads if h in text}


# ------------------------------------------------------------------------------------------ audit


def command_kind(use: dict, own: dict | None) -> str:
    if use["name"] != "Bash":
        return use["name"]
    cmd = use["input"].get("command") or ""
    if own and "jsonschema" in cmd and own["request_json"] in cmd and own["response"] in cmd:
        return "validation one-liner"
    if "run_e06.py" in cmd:
        sub = re.findall(r"run_e06\.py\s+(\w+)", cmd)
        return "harness: run_e06.py " + ",".join(sub)
    return "Bash"


REQ_LINE = re.compile(r"^[A-Z]+\d+n[0-9A-Za-z]+_p\d{4}[abc]\d{2}\t(.*)$", re.M)
REDIRECT = re.compile(r"(?:>>?|\btee\s+(?:-a\s+)?)\s*['\"]?([^\s'\";|&<>]+)")
PYWRITE = re.compile(r"open\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"][wa]")


def _written_paths(uses: list) -> set:
    """Files an agent wrote: Write/Edit targets, shell redirections, open(..., 'w') in inline Python."""
    out = set()
    for u in uses:
        i = u["input"]
        if u["name"] in ("Write", "Edit", "NotebookEdit") and i.get("file_path"):
            out.add(os.path.normpath(i["file_path"]))
        elif u["name"] == "Bash":
            cmd = i.get("command") or ""
            for m in list(REDIRECT.finditer(cmd)) + list(PYWRITE.finditer(cmd)):
                tok = m.group(1)
                if tok.startswith("/") and tok != "/dev/null":
                    out.add(os.path.normpath(tok))
                elif tok and not tok.startswith(("&", "/dev")):
                    for t2, absp in bash_paths(cmd, None):
                        if t2 == tok or absp.endswith("/" + tok):
                            out.add(os.path.normpath(absp))
            if "write_text(" in cmd or "json.dump(" in cmd:
                for t2, absp in bash_paths(cmd, None):
                    if re.search(r"llm/responses/[0-9a-f]{64}\.json$", absp):
                        out.add(os.path.normpath(absp))
    return out


def _benign_answer(a: dict, use: dict, written: set) -> str | None:
    """A rule-based reading of an answer agent's SUSPECT access (None = not explained)."""
    bad = [p for p in a["paths"] if p["class"] == "SUSPECT"]
    if not bad and a["reason"] == "search/listing command":
        return None
    reasons = []
    for p in bad:
        if p["reason"].startswith("own cell's llm/responses dir"):
            reasons.append("own cell's responses dir (mkdir / ls)")
        elif p["reason"] == "session scratchpad file":
            ap = p["path"] if p["path"].startswith("/") else str(REPO / p["path"])
            if os.path.normpath(ap) in written or ap.rstrip("/") == SCRATCH + "/scratchpad":
                reasons.append("scratch file the agent itself wrote")
            else:
                return None
        elif p["reason"] == "other repo path" and not os.path.exists(REPO / p["path"]) \
                and not any(ch in p["path"] for ch in "*?"):
            reasons.append("non-existent token (inline code), not a file access")
        else:
            return None
    return "; ".join(sorted(set(reasons))) or None


def audit_agent(path: Path, label: str, role: str) -> dict:
    t = parse_transcript(path)
    rec = {"agent_id": path.stem.replace("agent-", ""), "label": label, "role": role,
           "transcript": str(path), "tool_uses": len(t["uses"]), "tools": dict(Counter(u["name"] for u in t["uses"])),
           "attachments_injecting_files": t["edited_text_file"]}
    own = None
    if role == "answer":
        m = LABEL_RE.match(label)
        rnd, cell, task, h8 = m.groups()
        req_md = re.search(r"Request:\s*(\S+\.md)", t["prompt"]).group(1)
        resp = re.search(r"Answer goes to:\s*(\S+\.json)", t["prompt"]).group(1)
        full = HEX64.search(Path(req_md).name).group(0)
        own = {"request_md": req_md, "request_json": req_md[:-3] + ".json", "response": resp, "_hash": full}
        rec.update({"round": int(rnd), "cell": cell, "task": task, "hash8": h8, "hash": full,
                    "hash_matches_label": full.startswith(h8),
                    "own_paths": {k: rel(v) for k, v in own.items() if not k.startswith("_")}})
    accesses, by_class, split_c, flagged = [], Counter(), Counter(), []
    written = _written_paths(t["uses"])
    seen_results = []
    test_banner = 0
    marker_c = Counter()
    sdp_results = Counter()
    for u in t["uses"]:
        name = u["name"]
        res = t["results"].get(u["id"], "")
        paths = use_paths(u, t["cwd"])
        cls, why, plist = "NEUTRAL", "", []
        if name in WEB_TOOLS:
            cls, why = "FORBIDDEN", "web tool"
        elif name in ("Agent", "Task"):
            cls, why = "SUSPECT", "spawned a sub-agent"
        elif name == "StructuredOutput":
            cls, why = "ALLOWED", "final answer"
        elif name == "ToolSearch":
            q = str(u["input"].get("query", ""))
            cls, why = ("SUSPECT", "loaded a web tool") if re.search(r"web", q, re.I) else ("NEUTRAL", "tool schema")
        else:
            cls = "ALLOWED"
            for tok, absp in paths:
                if role == "answer":
                    c, w = classify_answer_path(absp, own)
                elif role == "driver":
                    c, w = classify_driver_path(absp)
                else:
                    c, w = classify_phase1_path(absp)
                plist.append({"path": rel(absp) or absp, "class": c, "reason": w})
                if SEV[c] > SEV[cls]:
                    cls, why = c, w
                elif not why:
                    why = w
            if name == "Bash":
                cmd = u["input"].get("command") or ""
                if WEB_CMD.search(cmd):
                    cls, why = "FORBIDDEN", "network command"
                own_only = plist and all(p["reason"].startswith(("own ", "pipeline interpreter", "null device",
                                                                   "working directory", "system interpreter"))
                                         for p in plist)
                if role == "answer" and SEARCH_CMD.search(cmd) and SEV[cls] < SEV["SUSPECT"] and not own_only:
                    cls, why = "SUSPECT", "search/listing command"
                for s in DO_NOT_OPEN_SUBSTR:  # names that are not path tokens (grep -v, module names)
                    if s in cmd and not any(p["reason"] == "Do-not-open file" for p in plist):
                        plist.append({"path": "<mention:%s>" % s, "class": "NOTE",
                                      "reason": "Do-not-open name in command (not a path token)"})
                        if SEV[cls] < SEV["NOTE"]:
                            cls, why = "NOTE", "Do-not-open name mentioned"
            if role == "driver" and name in ("Write", "Edit", "NotebookEdit"):
                cls, why = "SUSPECT", "driver edited a file"
            if not paths and name == "Bash" and not why:
                why = "no path"
        by_class[cls] += 1
        a = {"tool": name, "kind": command_kind(u, own), "class": cls, "reason": why, "paths": plist}
        sc = split_scan(res, _hint(u)) + split_scan(json.dumps(u["input"], ensure_ascii=False))
        if sc:
            a["test_reserve_lineheads"] = summarize_split(sc)
        split_c += sc
        if "EVAL-SETS" not in json.dumps(u["input"]) and "# EVAL-SETS" not in res:  # the guide names the banner
            test_banner += res.count("TEST SPLIT")
        if role == "answer":
            for mk in GOLD_MARKERS:
                n = res.count(mk)
                if n:
                    marker_c[mk] += n
        if role != "answer" and re.search(r"dila-sdp|sdp-T(1718|0262)|zhiyi-wenju", json.dumps(u["input"])) \
                and SDP_LONG:
            hits = {h for h in sdp_hits(res, SDP_LONG)
                    if GUARD.ALLOWED.get(h, ((None,),))[0] != GUARD.ANYWHERE}  # e.g. the sūtra title
            if hits:
                sdp_results[len(hits)] += 1
                a["sdp_heading_hits_in_result"] = {"count": len(hits),
                                                   "digests": sorted(digest(h) for h in hits)[:50]}
        if role == "answer" and cls == "SUSPECT":
            a["benign"] = _benign_answer(a, u, written)
        if name == "Read" and str(u["input"].get("file_path", "")).startswith(str(SESSION / "tool-results")):
            fp = u["input"]["file_path"]
            a["overflow_of_own_earlier_output"] = any(fp in r for r in seen_results)
        seen_results.append(res)
        accesses.append(a)
        if SEV[cls] >= SEV["NOTE"] or a.get("sdp_heading_hits_in_result"):
            flagged.append(a)
    rec["by_class"] = dict(by_class)
    rec["worst"] = max(by_class, key=lambda k: SEV[k]) if by_class else "NEUTRAL"
    rec["flagged_accesses"] = flagged
    rec["accesses"] = accesses
    rec["test_reserve_lineheads"] = summarize_split(split_c)
    rec["undocumented_test_or_reserve_lines_with_text"] = undocumented_text(split_c)
    rec["undocumented_test_lines_with_text"] = undocumented_test_text(split_c)
    rec["TEST_SPLIT_banner_in_results"] = test_banner
    if role == "answer":
        req_text = Path(own["request_md"]).read_text(encoding="utf-8")
        req_json_text = Path(own["request_json"]).read_text(encoding="utf-8")
        unexplained = {}
        for mk, n in marker_c.items():
            if mk not in req_text and mk not in req_json_text:
                unexplained[mk] = n
        rec["gold_markers_in_results"] = dict(marker_c)
        rec["gold_markers_not_in_own_request"] = unexplained
        rp = Path(own["response"])
        rec["response_exists"] = rp.exists()
        if rp.exists() and SDP_LONG:
            resp_text = rp.read_text(encoding="utf-8")
            joined = "".join(m.group(1) for m in REQ_LINE.finditer(req_text))  # phrases across line breaks
            novel = sdp_hits(resp_text, SDP_LONG) - sdp_hits(req_text + "\n" + joined, SDP_LONG)
            rec["sdp_headings_in_response_not_in_request"] = {
                "count": len(novel), "digests": sorted(digest(h) for h in novel)}
        rec["wrote_own_response"] = own["response"] in written
        rec["wrote_elsewhere"] = sorted(rel(w) or w for w in written - {own["response"]})
    return rec


def request_split_check() -> dict:
    """T34n1718 / T34n1723 text lines (<linehead>\\t<text>) per split in every request .md (counts)."""
    out = {}
    line_re = re.compile(r"^(T34n17(?:18|23)_p\d{4}[abc]\d{2})\t", re.M)
    for p in sorted(E06.glob("runs/*/llm/requests/*.md")):
        c = Counter(split_of_line(REG, lh) for lh in line_re.findall(p.read_text(encoding="utf-8")))
        if c:
            out[rel(str(p))] = dict(c)
    tot = Counter()
    for v in out.values():
        tot.update(v)
    bad = {k: v for k, v in out.items() if set(v) & {"test", "reserve"}}
    marker = {}
    for p in sorted(E06.glob("runs/*/llm/requests/*")):
        s = p.read_text(encoding="utf-8")
        hits = [m for m in ("reference-outlines", "dila-sdp", "dila-ybh", "zhiyi-wenju-sdp", "TEST SPLIT",
                            "draft-unreviewed", "seeded_by", "cbeta-mulu-kepan", "ybh-dila") if m in s]
        if hits:
            marker[rel(str(p))] = hits
    return {"request_md_files_with_split_text": len(out), "lines_by_split_total": dict(tot),
            "files_with_test_or_reserve_lines": bad, "gold_markers_in_request_files": marker}


def duplicate_hash_answers(answers: list) -> list:
    by = defaultdict(list)
    for a in answers:
        by[(a["hash"], a["task"])].append(a)
    out = []
    for (h, task), lst in by.items():
        cells = sorted({a["cell"] for a in lst})
        if len(lst) < 2:
            continue
        ent = {"hash8": h[:8], "task": task, "agents": [(a["agent_id"], a["cell"]) for a in lst], "cells": cells}
        resp = []
        for a in lst:
            p = REPO / a["own_paths"]["response"]
            resp.append(json.loads(p.read_text(encoding="utf-8")) if p.exists() else None)
        ent["responses_byte_identical"] = len({json.dumps(r, sort_keys=True) for r in resp}) == 1
        if all(r and isinstance(r.get("spans"), list) for r in resp):
            starts = [{s.get("node_id"): s.get("start") for s in r["spans"]} for r in resp]
            ends = [{s.get("node_id"): s.get("end") for s in r["spans"]} for r in resp]
            ids = set(starts[0]) | set(starts[1])
            ent["root_spans_agreement"] = {
                "nodes_union": len(ids), "nodes_both": len(set(starts[0]) & set(starts[1])),
                "same_start": sum(1 for i in ids if starts[0].get(i) == starts[1].get(i) is not None),
                "same_end": sum(1 for i in ids if ends[0].get(i) == ends[1].get(i) is not None)}
        out.append(ent)
    return out


def dharani_dev_check() -> dict:
    """DEV ONLY (Kuiji 陀羅尼品 subtree, readable per data/EVAL-SETS.md): which gold nodes the root-spans
    answers filled, by the gold's root_text.basis, and whether two independent answers to the identical
    request (hash 626ce7f0: hybrid-T0262-dharani-root and hybrid-T1723-dev) hit the gold starts. Counts only."""
    gold = json.loads((REPO / "data/reference-outlines/T0262/kuiji-xuanzan/outline.json").read_text(encoding="utf-8"))
    dev = []
    for n in gold["nodes"]:  # select by the dev split of the explained line BEFORE looking at anything else
        ex = ((n.get("locations") or {}).get("commentary") or {}).get("explained")
        if ex and split_of_line(REG, ex) == "dev":
            dev.append(n)
    key = lambda n: (n["locations"]["commentary"]["explained"].split(":")[0], n.get("heading_src"))
    gold_by = defaultdict(list)
    for n in dev:
        gold_by[key(n)].append(n)
    out = {"gold_dev_nodes": len(dev),
           "gold_dev_nodes_by_root_basis": dict(Counter(str((n["locations"].get("root_text") or {}).get("basis"))
                                                        for n in dev))}
    pred = json.loads((E06 / "runs/hybrid-T0262-dharani-root/outline.json").read_text(encoding="utf-8"))
    pred_by_id = {n["id"]: n for n in pred["nodes"]}
    for cell in ("hybrid-T0262-dharani-root", "hybrid-T1723-dev"):
        rp = E06 / "runs" / cell / "llm/responses" / "626ce7f030a1c3e4e396124da2bf7f505dbc6a8dcd53589358e9f234ac5ee460.json"
        spans = json.loads(rp.read_text(encoding="utf-8"))["spans"]
        c = Counter()
        for sp in spans:
            pn = pred_by_id.get(sp["node_id"])
            g = gold_by.get(key(pn), []) if pn else []
            if len(g) != 1:
                c["unmatched_to_unique_gold_node"] += 1
                continue
            rt = g[0]["locations"].get("root_text") or {}
            b = str(rt.get("basis"))
            c["answered:basis=" + b] += 1
            c["same_start_as_gold:basis=" + b] += int(sp["start"] == rt.get("start"))
            c["same_end_as_gold:basis=" + b] += int(sp["end"] == rt.get("end"))
        out["answer_" + cell] = dict(sorted(c.items()))
    return out


def e06_output_guard() -> dict:
    """tests/unit/test_sdp_eval_only_guard.py's check, applied to E06's (untracked) output files."""
    files = sorted(p for p in E06.iterdir() if p.is_file() and p.suffix in (".md", ".json", ".py"))
    files += [REPO / "experiments" / "E01-explicit-recovery" / "looks.json"]
    if not SDP_HEADS:
        return {"skipped": "sdp golds absent"}
    by_prefix = defaultdict(list)
    for h in SDP_HEADS:
        by_prefix[h[: GUARD.SHORT]].append(h)
    res = {}
    for p in files:
        if not p.exists():
            res[rel(str(p))] = {"missing": True}
            continue
        path = rel(str(p))
        text = p.read_text(encoding="utf-8")
        strict = path.startswith(GUARD.STRICT_PREFIXES)
        grams = {text[i: i + GUARD.SHORT] for i in range(len(text) - GUARD.SHORT + 1)}
        leaks, short_info = [], []
        for g in grams & by_prefix.keys():
            for h in by_prefix[g]:
                if h not in text or GUARD._allowed(path, h):
                    continue
                if strict or len(h) >= GUARD.LONG:
                    leaks.append(h)
                else:
                    short_info.append(h)
        trl = {"%s_p%s" % m for m in LH_RE.findall(text)}
        trl = {lh for lh in trl if split_of_line(REG, lh) in ("test", "reserve")}
        res[path] = {"guard_rule": "strict (>=3)" if strict else "long (>=5)",
                     "leaks": sorted((len(h), digest(h)) for h in leaks),
                     "short_3_4_char_hits_info_only": len(short_info),
                     "test_reserve_lineheads": len(trl),
                     "test_reserve_lineheads_not_in_committed_docs": len(trl - DOC_LH)}
    return {"files": res, "total_leaks": sum(len(v.get("leaks", [])) for v in res.values()),
            "sdp_headings_loaded": len(SDP_HEADS)}


def _require_transcripts() -> None:
    missing = [name for name in (SESSION_ENV, SCRATCHPAD_ENV) if not os.environ.get(name)]
    if missing:
        raise SystemExit("audit_leakage.py: set %s (the original Claude Code transcripts and scratchpad of "
                         "the session; see the module docstring)" % " and ".join(missing))
    if not SESSION.is_dir():
        raise SystemExit("audit_leakage.py: %s=%s is not a directory" % (SESSION_ENV, SESSION))


def main() -> int:
    _require_transcripts()
    lab_a = journal_labels(WF_ANSWER)
    lab_p = journal_labels(WF_PHASE1)
    answers, drivers, phase1 = [], [], []
    for aid, info in sorted(lab_a.items(), key=lambda kv: kv[1]["label"]):
        p = WF_ANSWER / ("agent-%s.jsonl" % aid)
        label = info["label"]
        if label.startswith("answer:"):
            answers.append(audit_agent(p, label, "answer"))
        else:
            drivers.append(audit_agent(p, label, "driver"))
    for aid, info in sorted(lab_p.items(), key=lambda kv: kv[1]["label"]):
        phase1.append(audit_agent(WF_PHASE1 / ("agent-%s.jsonl" % aid), info["label"], "phase1"))
    unlabelled = sorted({p.stem for p in WF_ANSWER.glob("agent-*.jsonl")} - {"agent-" + a for a in lab_a})

    def agg(lst):
        c = Counter()
        for r in lst:
            c.update(r["by_class"])
        return {"agents": len(lst), "tool_uses": sum(r["tool_uses"] for r in lst), "by_class": dict(c),
                "agents_by_worst": dict(Counter(r["worst"] for r in lst)),
                "agents_with_undocumented_test_or_reserve_text": sum(
                    1 for r in lst if r["undocumented_test_or_reserve_lines_with_text"]),
                "agents_with_undocumented_test_text": sum(1 for r in lst if r["undocumented_test_lines_with_text"]),
                "agents_with_TEST_SPLIT_banner_in_results": sum(1 for r in lst if r["TEST_SPLIT_banner_in_results"]),
                "do_not_open_hits": [(r["agent_id"], r["label"], x["tool"], p["path"], p["reason"])
                                     for r in lst for x in r["accesses"] for p in x["paths"]
                                     if "Do-not-open" in p["reason"]]}

    focus_cells = ("hybrid-T0262-dharani-root", "hybrid-T1723-dev", "hybrid-T0262-xu-root", "hybrid-T1718-dev",
                   "hybrid-T1718-devval", "hybrid-T1718-validation", "model-only-T0262-xu-root",
                   "model-only-T0262-dharani-root")
    focus = [{k: r[k] for k in ("agent_id", "label", "by_class", "worst", "gold_markers_not_in_own_request",
                                "sdp_headings_in_response_not_in_request", "wrote_own_response", "wrote_elsewhere",
                                "undocumented_test_or_reserve_lines_with_text") if k in r}
             for r in answers if r["cell"] in focus_cells]
    for f in focus:
        f["sdp_headings_in_response_not_in_request"] = (f.get("sdp_headings_in_response_not_in_request") or {}).get("count")
    doc = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "script": rel(__file__),
        "transcripts": {"answer_workflow": str(WF_ANSWER), "phase1_workflow": str(WF_PHASE1)},
        "policy": {
            "answer.ALLOWED": "own request .md/.json (same hash), own response, pipeline interpreter of the "
                              "validation one-liner, StructuredOutput",
            "answer.FORBIDDEN": "data/reference-outlines, data/raw/dila-sdp, data/raw/dila-ybh, data/raw/cbeta, "
                                "tests/, context/, skills/, docs/, another hash's request/response, "
                                "experiments/*/runs/*/outline*, metrics/score files, web tools/network commands",
            "answer.SUSPECT": "anything else (incl. same hash in another cell, search/listing commands)",
            "driver.FORBIDDEN": "gold / raw eval data / tests/fixtures / context/research / Do-not-open opened by hand",
            "phase1.FORBIDDEN": "Do-not-open files (data/EVAL-SETS.md); gold paths listed as NOTE",
            "test_reserve_scan": "T34n1718/T34n1723 lineheads of split test/reserve in tool results and inputs; "
                                 "'text' = >=4 CJK chars within 60 chars after the linehead on its line; "
                                 "'documented' = the linehead occurs in committed docs / harness code",
            "no_text": "paths, counts and sha256[:16] digests only; no source, gold or sdp text",
        },
        "documented_lineheads": len(DOC_LH),
        "unlabelled_transcripts": unlabelled,
        "aggregate": {"answer": agg(answers), "driver": agg(drivers), "phase1": agg(phase1),
                      "answer_flagged_suspect_or_forbidden": [
                          (r["agent_id"], r["label"], r["worst"]) for r in answers
                          if SEV[r["worst"]] >= SEV["SUSPECT"]],
                      "answer_gold_markers_not_in_own_request": {
                          r["agent_id"]: r["gold_markers_not_in_own_request"] for r in answers
                          if r.get("gold_markers_not_in_own_request")},
                      "answer_sdp_headings_in_response_not_in_request": {
                          "agents_with_any": sum(1 for r in answers
                                                 if (r.get("sdp_headings_in_response_not_in_request") or {}).get("count")),
                          "total": sum((r.get("sdp_headings_in_response_not_in_request") or {}).get("count", 0)
                                       for r in answers)},
                      "answer_wrote_outside_own_response": {r["agent_id"]: r["wrote_elsewhere"]
                                                            for r in answers if r["wrote_elsewhere"]},
                      "answer_missing_response_write": [r["agent_id"] for r in answers if not r["wrote_own_response"]],
                      "answer_responses_missing_on_disk": [r["agent_id"] for r in answers if not r["response_exists"]],
                      "answer_suspect_accesses": sum(1 for r in answers for x in r["accesses"]
                                                     if x["class"] == "SUSPECT"),
                      "answer_suspect_accesses_unexplained": [
                          (r["agent_id"], x["tool"], x["reason"]) for r in answers for x in r["accesses"]
                          if x["class"] == "SUSPECT" and not x.get("benign")],
                      "answer_suspect_benign_reasons": dict(Counter(
                          x["benign"] for r in answers for x in r["accesses"] if x.get("benign"))),
                      "overflow_reads_not_own": [(r["agent_id"], r["label"]) for r in answers + drivers + phase1
                                                 for x in r["accesses"]
                                                 if x.get("overflow_of_own_earlier_output") is False]},
        "focus": focus,
        "duplicate_hash_answers": duplicate_hash_answers(answers),
        "request_files": request_split_check(),
        "e06_outputs_sdp_guard": e06_output_guard(),
        "dharani_dev_check": dharani_dev_check(),
        "answer_agents": answers,
        "drivers": drivers,
        "phase1_agents": phase1,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    a = doc["aggregate"]
    print("answer agents:", json.dumps(a["answer"]))
    print("drivers:", json.dumps(a["driver"]))
    print("phase-1:", json.dumps(a["phase1"]))
    print("answer SUSPECT/FORBIDDEN:", a["answer_flagged_suspect_or_forbidden"])
    print("gold markers not in own request:", a["answer_gold_markers_not_in_own_request"])
    print("sdp headings in response not in request:", a["answer_sdp_headings_in_response_not_in_request"])
    print("request files:", json.dumps({k: v for k, v in doc["request_files"].items()
                                        if k != "files_with_test_or_reserve_lines"}),
          "files with test/reserve lines:", len(doc["request_files"]["files_with_test_or_reserve_lines"]))
    print("E06 outputs sdp guard: total leaks", doc["e06_outputs_sdp_guard"].get("total_leaks"))
    print("answer SUSPECT accesses:", a["answer_suspect_accesses"], "unexplained:", a["answer_suspect_accesses_unexplained"],
          "benign:", a["answer_suspect_benign_reasons"])
    print("missing response write:", a["answer_missing_response_write"], "missing on disk:",
          a["answer_responses_missing_on_disk"], "overflow reads not own:", a["overflow_reads_not_own"])
    print("dharani dev check:", json.dumps(doc["dharani_dev_check"], ensure_ascii=False))
    print("wrote", rel(str(OUT)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
