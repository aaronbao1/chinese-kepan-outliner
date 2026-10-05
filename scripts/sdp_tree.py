#!/usr/bin/env python3
"""scripts/sdp_tree.py — depth-first recursive fetch of sdp.chibs.edu.tw's getTreeNode API.

Called by scripts/fetch_dila_sdp.sh (Task 1 of the eval-dataset build) to materialize the whole
科判 tree of a sdp document (T0262 or T1718), which the reader UI otherwise only exposes one
level at a time as the user expands nodes in the ExtJS tree widget.

Input : network only. POST to <base>/exeQuery.php, body "id=<id>&getTreeNode=yes", returns a JSON
        array of that id's child nodes: [{"id","text","leaf"}, ...] (sdp.chibs.edu.tw's own
        eXist-db backend; see scripts/fetch_dila_sdp.sh's header for the endpoint's other mode,
        getHtml). <root-id> is queried the same way (e.g. "T0262", "T1718" — the document id, not
        a node id) to get its top-level children.
Output: writes <out-path>: a JSON array (server order) of the root's top-level children, each node
        {"id", "text", "leaf", "children": [...]} recursively — "children" is [] for a leaf node,
        and for a non-leaf node the same recursive expansion of its own getTreeNode call. A node
        whose getTreeNode call keeps failing with a non-JSON response even after --retries (a
        per-node server defect, observed 2026-09-22 for id=T1718D08_018: HTTP 200, body literally
        "query maybe faile\n", deterministic across repeated manual probes) is instead recorded as
        {"id", "text", "leaf": false, "children": null, "fetch_error": "<short reason>"} and the
        walk continues past it — never silently dropped, always counted (see "errors" below).
        Also prints one JSON object to stdout on success: {"root", "nodes", "leaves", "max_depth",
        "requests", "errors", "error_ids"} — "nodes" counts every node in the tree (root's children
        and all descendants, not the root id itself), "requests" the number of getTreeNode POSTs
        *this run* made (a resumed run does not recount requests a previous run already made and
        checkpointed), "errors"/"error_ids" the fetch_error nodes above.

Checkpointing / resume: after every getTreeNode request (success or recorded error), the tree built
so far is written to "<out-path>.partial.json" (atomic temp+rename). If that file exists when the
script starts, it is loaded as the starting tree instead of re-fetching from the root: any node that
already has a "children" key (a leaf already resolved to [], a non-leaf already expanded, or one
already carrying "fetch_error") is kept as is and not re-requested; only nodes still missing
"children" are fetched. This makes a long walk (T1718's is thousands of requests) safe to interrupt
and rerun. <out-path> itself is only written once the whole tree is fully resolved (every node has a
"children" key, possibly null+fetch_error) — at that point the checkpoint file is removed. A run
that raises ConnectionFailure (see below) leaves the checkpoint in place and writes nothing to
<out-path>; a rerun resumes it.

Usage : python3 scripts/sdp_tree.py <root-id> <out-path> [--base URL] [--sleep 0.4]
                                     [--timeout 30] [--retries 3] [--backoff 3.0]
        python3 scripts/sdp_tree.py --stats <path>   no network: re-derive {"nodes","leaves",
                                     "max_depth","errors"} from an already-written tree file (the
                                     same counting logic build_tree used when it wrote it), for
                                     fetch_dila_sdp.sh to report on a "keep" (checksum-unchanged,
                                     not re-fetched) run.

Politeness: depth-first, one HTTP request at a time (a node's children are fetched, then walked
before any sibling is requested), --sleep seconds between requests — same pacing as
fetch_dila_sdp.sh's curl loop. stdlib only (urllib.request, json, argparse, time).

Failure handling — two different things can go wrong, handled differently:
  * NodeFetchError: the server answered (an HTTP response came back) but the body would not parse
    as a JSON array even after --retries attempts with exponential backoff (--backoff * 2**attempt
    seconds). Treated as a defect in that one node: recorded as "fetch_error" (see Output above) and
    the walk continues with its siblings — this node just has no known children, and is not counted
    as a leaf.
  * ConnectionFailure: no HTTP response came back at all after --retries attempts (timeout, DNS,
    connection refused, ...) — treated as the server/network being down, not a defect in one node:
    stops the walk immediately, checkpoint already saved, exits 1 after printing "BLOCKED: ..." to
    stderr with what was fetched so far. Rerun once the server is reachable again to resume.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

UA = "chinese-workflow fetch script (research use; curl)"


class ConnectionFailure(RuntimeError):
    """No HTTP response at all after retries -- likely the server/network is down; abort the walk."""


class NodeFetchError(RuntimeError):
    """An HTTP response came back but never parsed as a JSON array, after retries -- a defect
    specific to this node; recorded on it, walk continues."""


def fetch_children(base: str, node_id: str, timeout: float, retries: int, backoff: float) -> list:
    """POST id=<node_id>&getTreeNode=yes; return the parsed JSON array of child nodes. Raises
    ConnectionFailure if no response ever came back, NodeFetchError if responses came back but
    never parsed, both only after `retries` attempts."""
    url = base.rstrip("/") + "/exeQuery.php"
    data = ("id=%s&getTreeNode=yes" % node_id).encode("utf-8")
    last_network_err: Exception | None = None
    last_parse_err: Exception | None = None
    last_body: str | None = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                url, data=data, method="POST", headers={"User-Agent": UA}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001 — no HTTP response at all
            last_network_err = e
            if attempt < retries:
                time.sleep(backoff * (2 ** (attempt - 1)))
                continue
            raise ConnectionFailure(
                "no response for id=%s after %d attempt(s): %s" % (node_id, retries, last_network_err)
            )
        last_body = body
        try:
            # strict=False: the server emits raw, unescaped control characters (observed: a literal
            # "\n" inside a node's "text", e.g. id=T0262D02_014's second child) inside JSON strings,
            # which is technically invalid per RFC 8259 but not something to fail the walk over
            parsed = json.loads(body, strict=False)
            if not isinstance(parsed, list):
                raise ValueError("response is not a JSON array: %r" % (body[:200],))
            return parsed
        except Exception as e:  # noqa: BLE001 — got a response, but not a JSON array
            last_parse_err = e
            if attempt < retries:
                time.sleep(backoff * (2 ** (attempt - 1)))
    raise NodeFetchError(
        "non-JSON response for id=%s after %d attempt(s): body=%r (%s)"
        % (node_id, retries, (last_body or "")[:80], last_parse_err)
    )


def _shell(node: dict) -> dict:
    """A fresh, unresolved node shell from a getTreeNode child entry (no "children" key yet)."""
    return {"id": node["id"], "text": node.get("text", ""), "leaf": bool(node.get("leaf"))}


def _resume_expand(base, nodes, depth, sleep, timeout, retries, backoff, stats, log, checkpoint) -> None:
    """Mutate `nodes` in place, filling in "children" (and "fetch_error" where applicable) for
    every entry that does not already have one -- so a node loaded from a checkpoint with
    "children" already present is skipped (not re-requested) but still walked into, resuming any
    of its own descendants that are still unresolved."""
    stats["max_depth"] = max(stats["max_depth"], depth)
    for node in nodes:
        stats["nodes"] += 1
        if "children" not in node:
            if node.get("leaf"):
                stats["leaves"] += 1
                node["children"] = []
            else:
                time.sleep(sleep)
                try:
                    kids = fetch_children(base, node["id"], timeout, retries, backoff)
                    stats["requests"] += 1
                    node["children"] = [_shell(k) for k in kids]
                    log(
                        "fetch  %-18s depth %2d  -> %2d children  (request %d, %d nodes so far)"
                        % (node["id"], depth + 1, len(kids), stats["requests"], stats["nodes"])
                    )
                    if not kids:
                        log("warning: %s has leaf=false but 0 children" % node["id"])
                except NodeFetchError as e:
                    stats["requests"] += 1
                    stats["errors"] += 1
                    stats["error_ids"].append(node["id"])
                    node["children"] = None
                    node["fetch_error"] = str(e)
                    log("ERROR (recorded on the node, continuing): %s" % e)
                checkpoint()  # one checkpoint write per network round-trip
        else:
            if node.get("fetch_error") is not None:
                stats["errors"] += 1
                stats["error_ids"].append(node["id"])
            elif node.get("leaf"):
                stats["leaves"] += 1
        if node.get("children"):
            _resume_expand(base, node["children"], depth + 1, sleep, timeout, retries, backoff, stats, log, checkpoint)


def count_tree(nodes: list, depth, stats) -> None:
    """Walk an already-fetched (or partially-fetched) tree, no network, and accumulate
    nodes/leaves/errors/max_depth into stats -- the same counting _resume_expand does while
    fetching, for --stats."""
    if not nodes:
        return
    stats["max_depth"] = max(stats["max_depth"], depth)
    for n in nodes:
        stats["nodes"] += 1
        if n.get("fetch_error") is not None:
            stats["errors"] += 1
        elif n.get("leaf"):
            stats["leaves"] += 1
        else:
            count_tree(n.get("children") or [], depth + 1, stats)


def build_tree(base, root_id, sleep, timeout, retries, backoff, stats, log, resume_top, checkpoint) -> list:
    """Return the root's top-level children, each recursively expanded; depth-first, one request
    at a time. resume_top, if not None, is a checkpointed top-level list to resume from instead of
    re-fetching the root."""
    if resume_top is not None:
        top = resume_top
        log("resuming from checkpoint: %d top-level node(s)" % len(top))
    else:
        kids = fetch_children(base, root_id, timeout, retries, backoff)
        stats["requests"] += 1
        top = [_shell(k) for k in kids]
        log("fetch  %-18s depth  1  -> %2d children  (request %d)" % (root_id, len(top), stats["requests"]))
        checkpoint(top)
    _resume_expand(base, top, 1, sleep, timeout, retries, backoff, stats, log, lambda: checkpoint(top))
    return top


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python3 scripts/sdp_tree.py",
        description="Depth-first recursive fetch of one sdp.chibs.edu.tw getTreeNode 科判 tree.",
    )
    ap.add_argument("root_id", nargs="?", help='document id, e.g. "T0262" or "T1718"')
    ap.add_argument("out_path", nargs="?", help="where to write the nested JSON tree")
    ap.add_argument("--base", default="http://sdp.chibs.edu.tw")
    ap.add_argument("--sleep", type=float, default=0.4, help="seconds between requests")
    ap.add_argument("--timeout", type=float, default=30.0, help="per-request timeout, seconds")
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--backoff", type=float, default=3.0, help="seconds, doubled each retry")
    ap.add_argument("--stats", metavar="PATH", help="no fetch: summarize an existing tree file")
    args = ap.parse_args(argv)

    if args.stats:
        stats = {"nodes": 0, "leaves": 0, "max_depth": 0, "errors": 0}
        with open(args.stats, encoding="utf-8") as f:
            tree = json.load(f)
        count_tree(tree, 1, stats)
        print(json.dumps({"root": args.stats, **stats}, ensure_ascii=False))
        return 0

    if not args.root_id or not args.out_path:
        ap.error("root_id and out_path are required unless --stats is given")

    checkpoint_path = args.out_path + ".partial.json"
    resume_top = None
    if os.path.exists(checkpoint_path):
        with open(checkpoint_path, encoding="utf-8") as f:
            resume_top = json.load(f)

    def save_checkpoint(top) -> None:
        tmp = checkpoint_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(top, f, ensure_ascii=False)
        os.replace(tmp, checkpoint_path)

    stats = {"nodes": 0, "leaves": 0, "max_depth": 0, "requests": 0, "errors": 0, "error_ids": []}
    log = lambda msg: print(msg, file=sys.stderr)  # noqa: E731

    try:
        tree = build_tree(
            args.base, args.root_id, args.sleep, args.timeout, args.retries, args.backoff,
            stats, log, resume_top, save_checkpoint,
        )
    except ConnectionFailure as e:
        print(
            "BLOCKED: %s (%d nodes resolved this run, %d requests, %d error node(s) recorded; "
            "checkpoint saved to %s -- rerun to resume)"
            % (e, stats["nodes"], stats["requests"], stats["errors"], checkpoint_path),
            file=sys.stderr,
        )
        return 1

    with open(args.out_path, "w", encoding="utf-8") as f:
        json.dump(tree, f, ensure_ascii=False)
        f.write("\n")
    if os.path.exists(checkpoint_path):
        os.remove(checkpoint_path)

    summary = {
        "root": args.root_id,
        "nodes": stats["nodes"],
        "leaves": stats["leaves"],
        "max_depth": stats["max_depth"],
        "requests": stats["requests"],
        "errors": stats["errors"],
        "error_ids": stats["error_ids"],
    }
    print(json.dumps(summary, ensure_ascii=False))
    if stats["errors"]:
        log("%d node(s) recorded with fetch_error (never resolved children): %s" % (stats["errors"], stats["error_ids"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
