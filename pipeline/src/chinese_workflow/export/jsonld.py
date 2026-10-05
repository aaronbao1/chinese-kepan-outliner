"""Knowledge-graph export v0 (plan M9, D20; docs/outliner-design.md §8): independent outline -> JSON-LD.

Input:  an independent outline, `outline.json` under profile zh-kepan (context/baseline/
        outline-schema-zh.json, D15), as a dict; optionally the id history of earlier exports.
Output: (1) one JSON-LD document per (work = metadata.root_text_id, scheme = metadata.scheme_id) in
        the shape of BDRC's ontology (R07 F20 VERIFIED; `core/bdo.ttl`, R07 S50): a `bdo:Outline`
        resource with attribution, one resource per outline node linked by `bdo:partOf`, ordered by
        `bdo:partIndex` / `bdo:partTreeIndex`, typed by `bdo:partType`, located by a
        `bdo:ContentLocation` whose start is BDRC's `bdo:contentLocationStatementCBETA`;
        (2) the updated id history (content key -> node URI), so URIs are minted once and stay stable.
        `load(jsonld)` re-imports the exported fields (the lossless round trip of M9's acceptance).

BDRC terms (checked against data/raw/bdrc/owl-schema/core/bdo.ttl): bdo:Outline, bdo:outlineOf,
bdo:Instance, bdo:partOf, bdo:partIndex, bdo:partTreeIndex, bdo:partType, bdo:PartType,
bdo:contentLocation, bdo:ContentLocation, bdo:contentLocationInstance,
bdo:contentLocationStatementCBETA. Everything under `cw:` is ours (the announced / explained pair,
which BDRC lacks, R07 F20; attribution; the end of a CBETA span; flags; counts); README.md lists it.
As plan §5 "Knowledge graph" sets out, the catalogue tree stays apart: works are referenced
by IRI (`<base>work/<CBETA file id>`), never described or given parts here.

Guards (design §3, plan §5): an outline with `metadata.eval_only: true` is refused; so is any document
that is a registered out-of-domain or eval-only gold of data/eval-sets.json (matched by path,
`metadata.source_file`, `text_id` + `scheme_id` or `root_text_id` + `scheme_id`). Model-only nodes
(`origin: inferred` under a `model-*` scheme, D21) are withheld unless `allow_model_only_levels`
covers their level (default 0: never). Unless a frozen outliner is named, nodes below the structure
levels 1–2 whose CBETA locators touch a test or reserve span of a split text are withheld and only
counted (design §2.4: no stage reads those spans; the Kuiji gold's skeleton is structure, §3).
A withheld node takes its subtree with it.

Imports chinese_workflow.common only (tests/unit/test_stage_boundaries.py).
"""

from __future__ import annotations

import copy
import uuid
from pathlib import Path
from urllib.parse import quote, unquote

from ..common import lineheads, splits
from ..common.jsonio import canonical, sha256_text
from ..common.paths import repo_relative

BDO = "http://purl.bdrc.io/ontology/core/"
SKOS = "http://www.w3.org/2004/02/skos/core#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
XSD = "http://www.w3.org/2001/XMLSchema#"
DEFAULT_BASE = "https://example.org/chinese-workflow/"
HISTORY_SCHEMA = "cw-export-id-history/1"
STRUCTURE_LEVELS = 2  # levels 1-2 are structure (design §3), exempt from the split-span withholding
BLOCKED_SPLITS = ("test", "reserve")
HEADING_LANG = "lzh"
PART_TYPE_PREFIX = "cw:partType/"  # the source's own part type, verbatim (cb:mulu @type, e.g. 品)
NODE_CLASS_PREFIX = "cw:nodeClass/"  # our node_class, used as partType when part_type is null


class ExportRefused(ValueError):
    """The document may not be exported (eval-only, or a registered OOD / eval-only gold)."""


# --------------------------------------------------------------------------------------- IRIs


def cw_namespace(base_uri: str) -> str:
    return base_uri + "ontology/"


def context(base_uri: str = DEFAULT_BASE) -> dict:
    """The @context: prefixes, IRI-valued properties, and the ordered lists (flags, withheld ids)."""
    return {
        "bdo": BDO,
        "cw": cw_namespace(base_uri),
        "skos": SKOS,
        "rdfs": RDFS,
        "xsd": XSD,
        "bdo:outlineOf": {"@type": "@id"},
        "bdo:partOf": {"@type": "@id"},
        "bdo:partType": {"@type": "@id"},
        "bdo:contentLocationInstance": {"@type": "@id"},
        "cw:flags": {"@container": "@list"},
        "cw:withheldModelOnly": {"@container": "@list"},
    }


def outline_identity(meta: dict) -> str:
    """'T09n0262/kuiji-xuanzan': the work (root text file id) and the scheme; one outline each."""
    return "%s/%s" % (meta.get("root_text_id") or meta.get("text_id"), meta["scheme_id"])


def outline_uri(base_uri: str, meta: dict) -> str:
    return base_uri + "outline/" + outline_identity(meta)


def work_uri(base_uri: str, file_id: str) -> str:
    """A work of the catalogue tree, referenced by its CBETA file id and never described here."""
    return base_uri + "work/" + file_id


def _mint(base_uri: str, identity: str, key: str) -> str:
    return base_uri + "node/" + str(uuid.uuid5(uuid.NAMESPACE_URL, "%snode/%s#%s"
                                               % (base_uri, identity, key)))


# ------------------------------------------------------------------------------- content keys


def _comm(n: dict) -> dict | None:
    return (n.get("locations") or {}).get("commentary")


def _root(n: dict) -> dict | None:
    return (n.get("locations") or {}).get("root_text")


def content_keys(nodes: list) -> dict:
    """{node id: content key}. The key hashes heading_src + commentary.explained + root_text.start +
    the parent's key, so it survives renumbering (a sibling inserted before a node changes its id and
    sibling_index, not its key). Siblings that tie on all three get their occurrence number (2nd, 3rd
    ... in document order) in the key."""
    keys: dict = {}
    seen: dict = {}
    for n in nodes:  # document order: a parent precedes its children
        parent_key = keys.get(n.get("parent_id"), "") if n.get("parent_id") else ""
        base = [parent_key, n.get("heading_src") or "", (_comm(n) or {}).get("explained"),
                (_root(n) or {}).get("start")]
        tie = canonical(base)
        seen[tie] = seen.get(tie, 0) + 1
        if seen[tie] > 1:
            base.append(seen[tie])
        keys[n["id"]] = sha256_text(canonical(base))
    return keys


def empty_history() -> dict:
    return {"schema": HISTORY_SCHEMA, "outlines": {}}


# ------------------------------------------------------------------------------------- guards


def _registry_identity(ds: dict) -> dict:
    fm = ds.get("file_metadata") or {}
    if fm:
        return fm
    parts = Path(str(ds.get("path", ""))).parts  # data/reference-outlines/<text>/<scheme>/outline.json
    if len(parts) == 5 and parts[1] == "reference-outlines":
        return {"text_id": parts[2], "scheme_id": parts[3]}
    return {}


def _matches(ds: dict, meta: dict, source_path: str | None) -> str | None:
    paths = {ds.get("path")} | set(ds.get("extra_paths") or [])
    if source_path and repo_relative(source_path) in paths:
        return "path"
    if meta.get("source_file") in paths:
        return "metadata.source_file"
    fm = _registry_identity(ds)
    scheme = meta.get("scheme_id")
    if fm.get("scheme_id") and fm["scheme_id"] == scheme:
        if fm.get("text_id") and fm["text_id"] == meta.get("text_id"):
            return "text_id + scheme_id"
        if fm.get("root_text_id") and fm["root_text_id"] == meta.get("root_text_id"):
            return "root_text_id + scheme_id"
    return None


def check_source_path(path, registry: dict | None = None) -> None:
    """Refuse a path that is a registered OOD or eval-only gold, before the file is even read."""
    registry = registry if registry is not None else splits.load_registry()
    rel = repo_relative(path)
    for ds in registry.get("datasets", []):
        if not _protected(ds):
            continue
        if rel in {ds.get("path")} | set(ds.get("extra_paths") or []):
            raise ExportRefused("%s is the registered gold %s (%s): never exported"
                                % (rel, ds["id"], _why(ds)))


def _protected(ds: dict) -> bool:
    return (splits.is_ood(ds) or splits.is_eval_only(ds)
            or (ds.get("file_metadata") or {}).get("eval_only") is True)


def _why(ds: dict) -> str:
    return "out-of-domain gold" if splits.is_ood(ds) else "eval-only gold"


def check_exportable(doc: dict, *, source_path=None, registry: dict | None = None) -> None:
    """Raise ExportRefused unless the outline may enter the knowledge graph."""
    meta = doc.get("metadata") or {}
    if meta.get("outline_profile") != "zh-kepan":
        raise ExportRefused("not a zh-kepan outline (metadata.outline_profile)")
    if not meta.get("scheme_id"):
        raise ExportRefused("metadata.scheme_id is required: one outline per (work, scheme)")
    if meta.get("eval_only") is not False:
        raise ExportRefused("metadata.eval_only is %r: eval-only outlines are never exported"
                            % meta.get("eval_only"))
    if not (meta.get("licence") or {}).get("id"):
        raise ExportRefused("metadata.licence.id is null: no licence grant, so eval-only "
                            "(outline-schema-zh.json metadata_zh rule); never exported")
    registry = registry if registry is not None else splits.load_registry()
    for ds in registry.get("datasets", []):
        if not _protected(ds):
            continue
        how = _matches(ds, meta, source_path)
        if how:
            raise ExportRefused("document matches the registered gold %s by %s (%s): never exported"
                                % (ds["id"], how, _why(ds)))


def _model_only(n: dict, meta: dict) -> bool:
    scheme = n.get("scheme_id") or meta.get("scheme_id") or ""
    return n.get("origin") == "inferred" and scheme.startswith("model-")


def _split_blocked(n: dict, registry: dict) -> bool:
    refs = [(_comm(n) or {}).get("announced"), (_comm(n) or {}).get("explained"),
            (_root(n) or {}).get("start"), (_root(n) or {}).get("end")]
    return any(lineheads.is_ref(r) and splits.split_of_line(registry, r) in BLOCKED_SPLITS
               for r in refs)


def select_nodes(doc: dict, *, allow_model_only_levels: int = 0, frozen: str | None = None,
                 registry: dict | None = None) -> tuple[list, list, int]:
    """(kept nodes, withheld model-only node ids, number of nodes withheld by the split guard).
    A withheld node's descendants are withheld with it and counted under the same reason."""
    meta = doc["metadata"]
    registry = registry if registry is not None else splits.load_registry()
    kept, model_only, split_count = [], [], 0
    withheld: dict = {}  # node id -> reason
    for n in doc["nodes"]:
        reason = withheld.get(n.get("parent_id"))
        if reason is None and _model_only(n, meta) and n["level"] > allow_model_only_levels:
            reason = "model-only"
        if (reason is None and not frozen and n["level"] > STRUCTURE_LEVELS
                and _split_blocked(n, registry)):
            reason = "split"
        if reason is None:
            kept.append(n)
            continue
        withheld[n["id"]] = reason
        if reason == "model-only":
            model_only.append(n["id"])
        else:
            split_count += 1
    return kept, model_only, split_count


# ------------------------------------------------------------------------------------- export


def _statement(ref: str) -> tuple[str, int | None]:
    """A CBETA ref -> (linehead for bdo:contentLocationStatementCBETA, character offset or None)."""
    if lineheads.is_ref(ref):
        r = lineheads.parse(ref)
        return r.linehead, r.offset
    return ref, None


def _point(ref: str | None, instance: str | None) -> dict:
    loc: dict = {"@type": "bdo:ContentLocation"}
    if instance:
        loc["bdo:contentLocationInstance"] = instance
    if ref is not None:
        stmt, off = _statement(ref)
        loc["bdo:contentLocationStatementCBETA"] = stmt
        if off is not None:
            loc["cw:charOffset"] = off
    return loc


def _default_files(meta: dict) -> tuple[str | None, str | None]:
    """(file of commentary positions, file of root-text spans) when a location names none."""
    comm = meta.get("commentary_id") if meta.get("outline_mode") == "sutra" else meta.get(
        "root_text_id")
    return comm, meta.get("root_text_id")


def _labels(src: str, en: str) -> list:
    out = []
    if src:
        out.append({"@value": src, "@language": HEADING_LANG})
    if en:
        out.append({"@value": en, "@language": "en"})
    return out


def _part_type_iri(n: dict) -> tuple[str, dict]:
    if n.get("part_type"):
        iri = PART_TYPE_PREFIX + quote(n["part_type"], safe="")
        return iri, {"@id": iri, "@type": "bdo:PartType",
                     "rdfs:label": {"@value": n["part_type"], "@language": HEADING_LANG}}
    cls = n.get("node_class") or "sutra-span"
    iri = NODE_CLASS_PREFIX + quote(cls, safe="")
    return iri, {"@id": iri, "@type": "bdo:PartType", "rdfs:label": cls}


def _node_resource(n: dict, uri: str, parent_uri: str, meta: dict, base_uri: str) -> tuple:
    """(the node's resource, its bdo:PartType resource)."""
    comm_file, root_file = _default_files(meta)
    part_iri, part_res = _part_type_iri(n)
    res: dict = {
        "@id": uri,
        "@type": ["bdo:Instance", "cw:OutlineNode"],
        "bdo:partOf": parent_uri,
        "bdo:partIndex": n["sibling_index"],
        "bdo:partTreeIndex": ".".join(tok.split("_", 1)[0] for tok in n["path"]),
        "bdo:partType": part_iri,
    }
    labels = _labels(n.get("heading_src") or "", n.get("heading_en") or "")
    if labels:
        res["skos:prefLabel"] = labels
    locs = n.get("locations") or {"scheme": "none"}
    rt = locs.get("root_text")
    if rt is not None:
        file_id = rt.get("text_id") or root_file
        loc = _point(rt.get("start"), work_uri(base_uri, file_id) if file_id else None)
        if rt.get("end") is not None:
            stmt, off = _statement(rt["end"])
            loc["cw:contentLocationEndStatementCBETA"] = stmt
            if off is not None:
                loc["cw:endCharOffset"] = off
        for key, prop in (("basis", "cw:basis"), ("end_basis", "cw:endBasis"), ("raw", "cw:raw"),
                          ("text_id", "cw:cbetaFileId")):
            if rt.get(key) is not None:
                loc[prop] = rt[key]
        res["bdo:contentLocation"] = loc
    cp = locs.get("commentary")
    if cp is not None:
        file_id = cp.get("text_id") or comm_file
        inst = work_uri(base_uri, file_id) if file_id else None
        if cp.get("announced") is not None:
            res["cw:commentaryAnnounced"] = _point(cp["announced"], inst)
        if cp.get("explained") is not None:
            res["cw:commentaryExplained"] = _point(cp["explained"], inst)
        if cp.get("raw") is not None:
            res["cw:commentaryRaw"] = cp["raw"]
        if cp.get("text_id") is not None:
            res["cw:commentaryFileId"] = cp["text_id"]
        if cp.get("announced") is None and cp.get("explained") is None:
            res["cw:commentaryUnlocated"] = True  # a position exists but is not located
    if locs.get("scheme") != "cbeta-kepan":
        res["cw:locationScheme"] = locs.get("scheme")
    if locs.get("raw") is not None:
        res["cw:locationRaw"] = locs["raw"]
    res["cw:origin"] = n.get("origin")
    if n.get("confidence") is not None:
        res["cw:confidence"] = n["confidence"]
    if n.get("evidence"):
        res["cw:evidence"] = n["evidence"]
    for key, prop in (("child_count_announced", "cw:childCountAnnounced"),
                      ("extent_announced", "cw:extentAnnounced"),
                      ("display_label", "cw:displayLabel"),
                      ("node_class", "cw:nodeClass"),
                      ("source_node_id", "cw:sourceNodeId"),
                      ("scheme_id", "cw:schemeId")):
        if n.get(key) is not None:
            res[prop] = n[key]
    if n.get("flags"):
        res["cw:flags"] = list(n["flags"])
    return res, part_res


def _outline_resource(meta: dict, base_uri: str, exported: int, model_only: list,
                      split_count: int, frozen: str | None) -> dict:
    res: dict = {
        "@id": outline_uri(base_uri, meta),
        "@type": "bdo:Outline",
        "bdo:outlineOf": work_uri(base_uri, meta.get("root_text_id") or meta.get("text_id")),
    }
    labels = _labels(meta.get("text_title_src") or "", meta.get("text_title_en") or "")
    if labels:
        res["skos:prefLabel"] = labels
    licence = meta.get("licence") or {}
    for prop, value in (
        ("cw:rootTextId", meta.get("root_text_id")),
        ("cw:textId", meta.get("text_id")),
        ("cw:schemeId", meta.get("scheme_id")),
        ("cw:outlineMode", meta.get("outline_mode")),
        ("cw:commentaryId", meta.get("commentary_id")),
        ("cw:goldStatus", meta.get("gold_status")),
        ("cw:seededBy", meta.get("seeded_by")),
        ("cw:cbetaRelease", meta.get("cbeta_release")),
        ("cw:licenceId", licence.get("id")),
        ("cw:sourceFile", meta.get("source_file")),
        ("cw:generatedBy", meta.get("generated_by")),
    ):
        if value is not None:
            res[prop] = value
    res["cw:exportedNodeCount"] = exported
    if model_only:
        res["cw:withheldModelOnly"] = list(model_only)
    if split_count:
        res["cw:withheldSplitCount"] = split_count
    if frozen:
        res["cw:frozen"] = frozen
    return res


def export(doc: dict, *, id_history: dict | None = None, base_uri: str = DEFAULT_BASE,
           allow_model_only_levels: int = 0, source_path=None, frozen: str | None = None,
           registry: dict | None = None) -> tuple[dict, dict]:
    """(JSON-LD document, updated id history). Raises ExportRefused (a ValueError) per the guards.

    id_history maps outline identity -> node content key -> URI; keys seen before keep their URI,
    new keys get a fresh one (uuid5 of base, identity and key, so an export without history is still
    deterministic). Entries are never removed: a node whose key changed gets a new URI and the old
    one stays retired. The input history is not modified."""
    registry = registry if registry is not None else splits.load_registry()
    check_exportable(doc, source_path=source_path, registry=registry)
    meta = doc["metadata"]
    kept, model_only, split_count = select_nodes(
        doc, allow_model_only_levels=allow_model_only_levels, frozen=frozen, registry=registry)

    history = copy.deepcopy(id_history) if id_history else empty_history()
    if history.get("schema") != HISTORY_SCHEMA:
        raise ValueError("id history schema %r, expected %r" % (history.get("schema"),
                                                                HISTORY_SCHEMA))
    identity = outline_identity(meta)
    entry = history["outlines"].setdefault(identity, {"uri": outline_uri(base_uri, meta),
                                                      "nodes": {}})
    known = entry["nodes"]
    taken = {u: k for k, u in known.items()}
    keys = content_keys(doc["nodes"])

    uris: dict = {}
    for n in kept:
        key = keys[n["id"]]
        uri = known.get(key)
        if uri is None:
            uri = _mint(base_uri, identity, key)
            if uri in taken and taken[uri] != key:
                raise ValueError("id history already gives %s to another node" % uri)
            known[key] = uri
            taken[uri] = key
        uris[n["id"]] = uri

    graph = [_outline_resource(meta, base_uri, len(kept), model_only, split_count, frozen)]
    part_types: dict = {}
    for n in kept:
        parent_uri = uris[n["parent_id"]] if n.get("parent_id") else entry["uri"]
        res, part_res = _node_resource(n, uris[n["id"]], parent_uri, meta, base_uri)
        graph.append(res)
        part_types[part_res["@id"]] = part_res
    graph.extend(part_types[k] for k in sorted(part_types))

    history["outlines"] = {k: _sorted_entry(v) for k, v in sorted(history["outlines"].items())}
    return {"@context": context(base_uri), "@graph": graph}, history


def _sorted_entry(entry: dict) -> dict:
    return {"uri": entry["uri"], "nodes": dict(sorted(entry["nodes"].items()))}


# --------------------------------------------------------------------------------------- load


def _as_list(v) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _ref(stmt: str | None, off: int | None) -> str | None:
    if stmt is None:
        return None
    return lineheads.with_offset(stmt, off) if off is not None else stmt


def _labels_of(res: dict) -> tuple[str, str]:
    src = en = ""
    for lab in _as_list(res.get("skos:prefLabel")):
        if lab.get("@language") == "en":
            en = lab.get("@value", "")
        else:
            src = lab.get("@value", "")
    return src, en


def _compact(iri: str, cw_ns: str) -> str:
    return "cw:" + iri[len(cw_ns):] if iri.startswith(cw_ns) else iri


def load(jsonld: dict) -> dict:
    """Re-import an exported document: {'metadata': {...}, 'nodes': [...]} with nodes in document
    order (sorted by partTreeIndex) and zh-kepan field names. Reconstructs, per node: id and path
    (from bdo:partTreeIndex), level, parent_id (from bdo:partOf, checked against the tree index),
    sibling_index, heading_src, heading_en, origin, confidence, evidence, locations (commentary
    announced / explained / raw / text_id; root_text start / end / basis / end_basis / raw /
    text_id), child_count_announced, extent_announced, flags, display_label, node_class, part_type,
    source_node_id, scheme_id, and the node's URI. Reads the shape export() writes (not arbitrary
    JSON-LD)."""
    ctx = jsonld.get("@context") or {}
    cw_ns = ctx.get("cw", cw_namespace(DEFAULT_BASE))
    graph = jsonld.get("@graph") or []
    outlines = [r for r in graph if r.get("@type") == "bdo:Outline"]
    if len(outlines) != 1:
        raise ValueError("expected one bdo:Outline, found %d" % len(outlines))
    ol = outlines[0]
    meta = {
        "outline_uri": ol["@id"],
        "root_text_id": ol.get("cw:rootTextId"),
        "text_id": ol.get("cw:textId"),
        "scheme_id": ol.get("cw:schemeId"),
        "outline_mode": ol.get("cw:outlineMode"),
        "commentary_id": ol.get("cw:commentaryId"),
        "gold_status": ol.get("cw:goldStatus"),
        "seeded_by": ol.get("cw:seededBy"),
        "cbeta_release": ol.get("cw:cbetaRelease"),
        "licence_id": ol.get("cw:licenceId"),
        "source_file": ol.get("cw:sourceFile"),
        "generated_by": ol.get("cw:generatedBy"),
        "exported_node_count": ol.get("cw:exportedNodeCount"),
        "withheld_model_only": list(ol.get("cw:withheldModelOnly") or []),
        "withheld_split_count": ol.get("cw:withheldSplitCount", 0),
    }
    meta["text_title_src"], meta["text_title_en"] = _labels_of(ol)

    res_nodes = [r for r in graph if "cw:OutlineNode" in _as_list(r.get("@type"))]
    by_uri: dict = {}
    for r in res_nodes:
        idx = [int(x) for x in r["bdo:partTreeIndex"].split(".")]
        path = ["%d_%d" % (v, lv) for lv, v in enumerate(idx, 1)]
        by_uri[r["@id"]] = (r, idx, path)
    nodes = []
    for r, idx, path in sorted(by_uri.values(), key=lambda t: t[1]):
        nid = ".".join(path)
        if r["bdo:partOf"] == ol["@id"]:
            parent_id = None
        else:
            parent_id = ".".join(by_uri[r["bdo:partOf"]][2])
        if parent_id != (".".join(path[:-1]) or None) or r["bdo:partIndex"] != idx[-1]:
            raise ValueError("%s: bdo:partOf / bdo:partIndex disagree with bdo:partTreeIndex" % nid)
        src, en = _labels_of(r)
        part = _compact(r.get("bdo:partType", ""), cw_ns)
        n = {
            "id": nid,
            "uri": r["@id"],
            "level": len(path),
            "path": path,
            "parent_id": parent_id,
            "sibling_index": r["bdo:partIndex"],
            "heading_src": src,
            "heading_en": en,
            "origin": r.get("cw:origin"),
        }
        if "cw:confidence" in r:
            n["confidence"] = r["cw:confidence"]
        n["evidence"] = r.get("cw:evidence", "")
        n["locations"] = _load_locations(r)
        n["child_count_announced"] = r.get("cw:childCountAnnounced")
        n["extent_announced"] = r.get("cw:extentAnnounced")
        n["flags"] = list(r.get("cw:flags") or [])
        n["display_label"] = r.get("cw:displayLabel")
        n["node_class"] = r.get("cw:nodeClass")
        n["part_type"] = (unquote(part[len(PART_TYPE_PREFIX):])
                          if part.startswith(PART_TYPE_PREFIX) else None)
        n["source_node_id"] = r.get("cw:sourceNodeId")
        if "cw:schemeId" in r:
            n["scheme_id"] = r["cw:schemeId"]
        nodes.append(n)
    for k, n in enumerate(nodes, 1):
        n["order"] = k
    return {"metadata": meta, "nodes": nodes}


def _load_point(loc: dict | None) -> str | None:
    if loc is None:
        return None
    return _ref(loc.get("bdo:contentLocationStatementCBETA"), loc.get("cw:charOffset"))


def _load_locations(r: dict) -> dict:
    locs: dict = {"scheme": r.get("cw:locationScheme", "cbeta-kepan")}
    if locs["scheme"] == "cbeta-kepan":
        commentary = None
        ann, exp = r.get("cw:commentaryAnnounced"), r.get("cw:commentaryExplained")
        if ann or exp or r.get("cw:commentaryUnlocated") or "cw:commentaryRaw" in r \
                or "cw:commentaryFileId" in r:
            commentary = {"announced": _load_point(ann), "explained": _load_point(exp)}
            if "cw:commentaryFileId" in r:
                commentary["text_id"] = r["cw:commentaryFileId"]
            if "cw:commentaryRaw" in r:
                commentary["raw"] = r["cw:commentaryRaw"]
        root_text = None
        loc = r.get("bdo:contentLocation")
        if loc is not None:
            root_text = {
                "start": _load_point(loc),
                "end": _ref(loc.get("cw:contentLocationEndStatementCBETA"),
                            loc.get("cw:endCharOffset")),
                "basis": loc.get("cw:basis"),
            }
            for prop, key in (("cw:endBasis", "end_basis"), ("cw:raw", "raw"),
                              ("cw:cbetaFileId", "text_id")):
                if prop in loc:
                    root_text[key] = loc[prop]
        locs["commentary"] = commentary
        locs["root_text"] = root_text
    if "cw:locationRaw" in r:
        locs["raw"] = r["cw:locationRaw"]
    return locs


# ---------------------------------------------------------------------------------------- run


def run(outline_path, out_path, *, id_history_path=None, base_uri: str = DEFAULT_BASE,
        allow_model_only_levels: int = 0, frozen: str | None = None) -> dict:
    """Read outline.json, export it, write OUT.jsonld (and the id history when a path is given).
    Returns the outline resource of the export (its counts say what was withheld)."""
    from ..common.jsonio import read_json, write_json

    registry = splits.load_registry()
    check_source_path(outline_path, registry)  # before the file is read
    doc = read_json(outline_path)
    history = None
    if id_history_path and Path(id_history_path).exists():
        history = read_json(id_history_path)
    graph, history = export(doc, id_history=history, base_uri=base_uri,
                            allow_model_only_levels=allow_model_only_levels,
                            source_path=outline_path, frozen=frozen, registry=registry)
    write_json(graph, out_path)
    if id_history_path:
        write_json(history, id_history_path)
    return graph["@graph"][0]
