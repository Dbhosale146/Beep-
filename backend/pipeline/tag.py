"""Tag each post with a role and a city using Google Gemini.

Shape of the call, verified against google-genai 3.3.0 and the live docs on
2026-11-16:

    client.interactions.create(
        model=...,
        input=prompt,
        response_format={"type": "text", "mime_type": "application/json",
                         "schema": <json schema dict>},
        generation_config={"temperature": 0, "thinking_level": "minimal"},
    )
    -> interaction.output_text, interaction.usage

Three things keep this honest and cheap:

  * The taxonomy goes into the schema as `enum`, so constrained decoding makes
    an off-taxonomy answer impossible rather than merely unlikely.
  * We validate every response against config/taxonomy.yaml anyway. The schema
    could drift from the YAML, and a post could come back missing. One retry,
    then the post is marked Untagged. We never guess a tag ourselves.
  * Results are cached by a hash of the post's content, so a daily run only
    pays for posts it has not seen.
"""

import hashlib
import json
import logging
import time
from datetime import datetime, timezone

from pipeline.config import ROOT, data_path, require_env, settings, taxonomy

log = logging.getLogger(__name__)

# Bumping this invalidates the whole tag cache, which is the point: a changed
# prompt must not be mixed with answers from the old one.
#   tag_v1 -> first version
#   tag_v2 -> added the "Pan India" rule for country/state-only locations,
#             and spelled out that a suburb counts as its city
PROMPT_VERSION = "tag_v2"
UNTAGGED = "Untagged"


# --------------------------------------------------------------------------
# schema + prompt
# --------------------------------------------------------------------------

def build_schema(roles, cities):
    """Plain JSON Schema dict, built by hand.

    Short property names ("i", "r", "c", "f") on purpose: the Gemini docs warn
    that property-name length and enum size both add states to the constrained
    decoding grammar, and an oversized schema is rejected with 400.
    """
    return {
        "type": "object",
        "properties": {
            "tags": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "i": {"type": "integer", "description": "the post index given"},
                        "r": {"type": "string", "enum": list(roles)},
                        "c": {"type": "string", "enum": list(cities)},
                        "f": {"type": "boolean", "description": "is_fresher"},
                    },
                    "required": ["i", "r", "c", "f"],
                },
            }
        },
        "required": ["tags"],
    }


def load_prompt():
    return (ROOT / "prompts" / (PROMPT_VERSION + ".txt")).read_text(encoding="utf-8")


def render_prompt(batch, roles, cities):
    chars = settings()["export"]["llm_description_chars"]
    lines = []
    for index, post in enumerate(batch):
        lines.append(
            "[%d] title: %s\n    company: %s\n    location: %s\n    description: %s"
            % (
                index,
                post.get("title") or "",
                post.get("company") or "",
                post.get("raw_location") or "",
                (post.get("description") or "")[:chars],
            )
        )
    return (
        load_prompt()
        .replace("{ROLES}", "\n".join("  - " + r for r in roles))
        .replace("{CITIES}", "\n".join("  - " + c for c in cities))
        .replace("{POSTS}", "\n\n".join(lines))
    )


# --------------------------------------------------------------------------
# cache
# --------------------------------------------------------------------------

def cache_key(post):
    """Hash of the fields that could change the answer."""
    parts = [
        post.get("title") or "",
        post.get("company") or "",
        post.get("raw_location") or "",
        (post.get("description") or "")[:600],
        PROMPT_VERSION,
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]


def load_cache():
    path = data_path("tag_cache")
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("tag cache unreadable, starting empty: %s", e)
        return {}


def save_cache(cache):
    data_path("tag_cache").write_text(
        json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8"
    )


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------

def validate(payload, batch_size, roles, cities):
    """Turn a raw response into {index: tag dict}, dropping anything invalid.

    Returns (valid_by_index, problems). A partially valid response is useful:
    we keep the good rows and only retry if something is missing.
    """
    problems = []
    valid = {}

    if not isinstance(payload, dict) or not isinstance(payload.get("tags"), list):
        return {}, ["response is not an object with a tags list"]

    for item in payload["tags"]:
        if not isinstance(item, dict):
            problems.append("tag entry is not an object")
            continue
        index = item.get("i")
        if not isinstance(index, int) or not (0 <= index < batch_size):
            problems.append("index out of range: %r" % (index,))
            continue
        if item.get("r") not in roles:
            problems.append("role not in taxonomy: %r" % (item.get("r"),))
            continue
        if item.get("c") not in cities:
            problems.append("city not in taxonomy: %r" % (item.get("c"),))
            continue
        if not isinstance(item.get("f"), bool):
            problems.append("is_fresher not a bool: %r" % (item.get("f"),))
            continue
        valid[index] = {"role": item["r"], "city": item["c"], "is_fresher": item["f"]}

    missing = [i for i in range(batch_size) if i not in valid]
    if missing:
        problems.append("missing indexes: %s" % missing)
    return valid, problems


# --------------------------------------------------------------------------
# usage log
# --------------------------------------------------------------------------

def log_usage(usage, model, batch_size, attempt):
    """One JSON line per LLM call. This file is the whole cost report.

    total_thought_tokens is recorded separately because thinking tokens bill
    at the OUTPUT rate. Counting only total_output_tokens would under-report
    cost per 1,000 posts.
    """
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "posts_in_call": batch_size,
        "attempt": attempt,
        "input_tokens": getattr(usage, "total_input_tokens", None) or 0,
        "output_tokens": getattr(usage, "total_output_tokens", None) or 0,
        "thought_tokens": getattr(usage, "total_thought_tokens", None) or 0,
        "cached_tokens": getattr(usage, "total_cached_tokens", None) or 0,
        "total_tokens": getattr(usage, "total_tokens", None) or 0,
    }
    with open(data_path("usage_log"), "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return record


# --------------------------------------------------------------------------
# the call
# --------------------------------------------------------------------------

def make_client():
    # Imported here so the rest of the pipeline runs without the SDK installed.
    from google import genai

    return genai.Client(api_key=require_env(settings()["llm"]["api_key_env"]))


def call_model(client, prompt, schema, cfg, batch_size, attempt):
    interaction = client.interactions.create(
        model=cfg["model"],
        input=prompt,
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": schema,
        },
        generation_config=cfg["generation_config"],
    )
    usage = log_usage(interaction.usage, cfg["model"], batch_size, attempt)
    return interaction.output_text, usage


def tag_batch(client, batch, schema, roles, cities, cfg):
    """Tag one batch. Up to 1 + max_retries attempts, then Untagged."""
    prompt = render_prompt(batch, roles, cities)
    attempts = cfg["max_retries"] + 1
    valid = {}

    for attempt in range(1, attempts + 1):
        try:
            text, _ = call_model(client, prompt, schema, cfg, len(batch), attempt)
            payload = json.loads(text)
        except Exception as e:
            log.warning("    attempt %d failed: %s", attempt, e)
            if attempt < attempts:
                time.sleep(2)
            continue

        valid, problems = validate(payload, len(batch), roles, cities)
        if not problems:
            return valid, None
        log.warning("    attempt %d invalid: %s", attempt, "; ".join(problems[:3]))
        if attempt < attempts:
            time.sleep(2)

    return valid, "invalid_after_retry"


def tag_all(posts):
    """Tag every post, using the cache. Returns (posts, counts)."""
    cfg = settings()["llm"]
    tax = taxonomy()
    roles = list(tax["roles"])
    cities = list(tax["cities"].keys())
    schema = build_schema(roles, cities)

    cache = load_cache()
    counts = {
        "input": len(posts),
        "from_cache": 0,
        "sent_to_llm": 0,
        "llm_calls": 0,
        "tagged": 0,
        "untagged": 0,
    }

    todo = []
    for post in posts:
        key = cache_key(post)
        post["_cache_key"] = key
        if key in cache:
            post.update(cache[key])
            counts["from_cache"] += 1
        else:
            todo.append(post)

    log.info("tagging: %d cached, %d to send", counts["from_cache"], len(todo))

    if todo:
        client = make_client()
        size = cfg["batch_size"]
        for start in range(0, len(todo), size):
            batch = todo[start : start + size]
            log.info("  batch %d-%d of %d", start + 1, start + len(batch), len(todo))
            valid, error = tag_batch(client, batch, schema, roles, cities, cfg)
            counts["llm_calls"] += 1
            counts["sent_to_llm"] += len(batch)

            for index, post in enumerate(batch):
                tags = valid.get(index)
                if tags is None:
                    # Never guess. Mark it and move on.
                    tags = {"role": UNTAGGED, "city": UNTAGGED, "is_fresher": True}
                else:
                    cache[post["_cache_key"]] = tags
                post.update(tags)

        save_cache(cache)

    for post in posts:
        post.pop("_cache_key", None)
        if post.get("role") == UNTAGGED:
            counts["untagged"] += 1
        else:
            counts["tagged"] += 1

    return posts, counts
