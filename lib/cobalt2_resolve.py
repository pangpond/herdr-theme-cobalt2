"""Resolve an agent id Herdr reports but `cobalt2_marks.MARKS` does not cover.

The mark table is an exact-match dict of agent ids. Herdr recognizes more
harnesses than have artwork, and its ids drift (`github_copilot` vs `copilot`,
`open_code` vs `opencode`), so any id outside the table renders an empty logo
column. That is the gap this closes.

The judgment is "which product does this identifier name", which no lookup or
rule in this repository can answer for an id nobody has seen yet. It is asked
once, at decision time, through TypeSafe's System One API, and the verdict is
cached into the plugin's own config so the sidebar hooks stay stdlib-only,
offline, and instant.

Nothing here runs on a hook path. `bin/agent-marks` only calls it behind
`--resolve-unknown`, and every failure is soft: the caller falls back to
clearing the token, which is exactly today's behavior.

Stdlib only; urllib rather than the TypeSafe SDK, because Herdr runs plugin
commands with no site packages.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, NamedTuple

import cobalt2_config
import cobalt2_marks

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"
API_KEY_ENV = "TYPESAFE_API_KEY"

#: The cache lives with the rest of the plugin's config handling.
NO_MARK = cobalt2_config.NO_MARK

#: A Choice needs enough certainty to be worth painting. Below this the caller
#: keeps today's behavior and leaves the column empty.
CONFIDENCE_FLOOR = 0.6
#: The generic mark is only worth using when the id really is an agent. Branded
#: marks do not consult this: a confident brand match is its own evidence.
AGENT_FLOOR = 0.6

#: One entry per distinct mark, described by the product it was drawn for.
#: Keys are the canonical `MARKS` key for that codepoint; `test_cobalt2.py`
#: asserts this covers every mark, so a new mark cannot be added without one.
BRANDS: dict[str, str] = {
    "claude": "Anthropic's Claude Code CLI",
    "codex": "OpenAI's Codex CLI",
    "opencode": "opencode, the open-source terminal coding agent",
    "omp": "Oh My Pi (omp), the Pi coding harness",
    "cline": "Cline, the autonomous coding agent",
    "mastracode": "Mastra Code",
    "kimi": "Moonshot AI's Kimi CLI",
    "kilo": "Kilo Code",
    "maki": "Maki",
    "cursor": "Cursor's agent CLI",
    "grok": "xAI's Grok CLI",
    "copilot": "GitHub Copilot CLI",
    "gemini": "Google's Gemini CLI",
    "kiro": "AWS Kiro",
    "droid": "Factory's Droid CLI",
    "hermes": "Nous Research's Hermes agent",
    "agy": "Google Antigravity",
    "muse": "Muse",
    "amp": "Sourcegraph's Amp",
    "devin": "Cognition's Devin",
    "qwen": "Alibaba's Qwen Code",
    "qodercli": "Alibaba's Qoder CLI",
}

#: Returned by the Choice when the id names no coding agent at all.
NOT_AN_AGENT = "not_an_agent"


class ResolveError(RuntimeError):
    """Any reason a verdict could not be obtained. Always recoverable."""


class Verdict(NamedTuple):
    #: A `MARKS` key to use, or None to leave the column empty.
    mark: str | None
    #: The raw Choice option, kept for logging and for the cache.
    choice: str
    confidence: float
    #: Probability the id names a coding agent at all.
    is_agent: float

    @property
    def cacheable(self) -> str | None:
        """What to store, or None when the answer was too uncertain to keep.

        An uncertain answer is not cached, so a later model or a better id can
        be asked again instead of being pinned to a guess.
        """
        if self.confidence < CONFIDENCE_FLOOR:
            return None
        if self.choice == NOT_AN_AGENT:
            return NO_MARK
        return self.mark


def questions() -> dict[str, Any]:
    """The two judgments, asked together over the same state.

    They are independent, so one request answers both; the Noul is only read
    when the Choice lands on the generic bucket.
    """
    criteria = dict(BRANDS)
    criteria[cobalt2_marks.GENERIC] = (
        "A real AI coding agent or harness, but not any of the branded products "
        "listed above; it needs the generic agent mark"
    )
    criteria[NOT_AN_AGENT] = (
        "Not an AI coding agent at all: a shell, editor, language runtime, build "
        "tool, or unrelated process"
    )
    return {
        "mark": {
            "type": "choice",
            "instructions": (
                "A terminal multiplexer reports the AI coding agent running inside a "
                "pane as the identifier in `agent.id`. Each option below is a sidebar "
                "mark drawn for one specific product. Which product does this "
                "identifier name? Identifiers are lowercase, often abbreviated, and "
                "may be a CLI binary name, a package name, or a vendor's internal id."
            ),
            "criteria": criteria,
        },
        "is_coding_agent": {
            "type": "noul",
            "instructions": (
                "Does this identifier name an AI coding agent or agentic coding harness?"
            ),
            "criteria": {
                "true": "An AI coding agent, assistant CLI, or agentic coding harness",
                "false": "A shell, editor, runtime, build tool, or any non-agent process",
            },
        },
    }


def api_key(env: dict[str, str] | None = None) -> str:
    environ = env if env is not None else os.environ
    key = environ.get(API_KEY_ENV, "").strip()
    if not key:
        raise ResolveError(
            f"{API_KEY_ENV} is not set; export it to resolve unknown agents"
        )
    return key


def endpoint(env: dict[str, str] | None = None) -> str:
    environ = env if env is not None else os.environ
    return environ.get("TYPESAFE_ENDPOINT") or ENDPOINT


def _post(payload: dict[str, Any], key: str, url: str, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        with error:
            detail = error.read().decode(errors="replace").strip()[:200]
        raise ResolveError(f"TypeSafe returned HTTP {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise ResolveError(f"could not reach TypeSafe: {error.reason}") from error
    except (TimeoutError, OSError) as error:
        raise ResolveError(f"could not reach TypeSafe: {error}") from error
    except json.JSONDecodeError as error:
        raise ResolveError(f"TypeSafe sent malformed JSON: {error}") from error


def resolve(
    agent: str,
    timeout: float = 15.0,
    env: dict[str, str] | None = None,
) -> Verdict:
    """Ask which existing mark an unknown agent id should use.

    Raises ResolveError for anything the caller should treat as "no answer".
    """
    payload = {
        "state": {"agent": {"id": agent}},
        "model": MODEL,
        "questions": questions(),
    }
    body = _post(payload, api_key(env), endpoint(env), timeout)
    answers = body.get("answers")
    if not isinstance(answers, dict) or "mark" not in answers:
        raise ResolveError(f"TypeSafe sent no mark answer: {body!r:.200}")

    mark_answer = answers["mark"]
    choice = mark_answer.get("choice")
    confidence = float(mark_answer.get("confidence", 0.0))
    is_agent = float(answers.get("is_coding_agent", {}).get("noul", 0.0))
    if not isinstance(choice, str):
        raise ResolveError(f"TypeSafe sent no choice: {mark_answer!r:.200}")

    return Verdict(
        mark=_mark_for(choice, confidence, is_agent),
        choice=choice,
        confidence=confidence,
        is_agent=is_agent,
    )


def _mark_for(choice: str, confidence: float, is_agent: float) -> str | None:
    """Apply this plugin's risk policy to a raw answer.

    A wrong glyph is cosmetic and a blank column is the status quo, so the
    floors are deliberately mild. The generic bucket carries the extra Noul
    check because it is the one outcome that paints a mark without the model
    having recognized anything specific.
    """
    if confidence < CONFIDENCE_FLOOR or choice == NOT_AN_AGENT:
        return None
    if choice == cobalt2_marks.GENERIC:
        return cobalt2_marks.GENERIC if is_agent >= AGENT_FLOOR else None
    return choice if choice in cobalt2_marks.MARKS else None
