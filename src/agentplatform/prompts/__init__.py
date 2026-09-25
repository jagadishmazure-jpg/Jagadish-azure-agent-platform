"""Prompt layer: versioned prompt pack (markdown + front matter) bound to output schemas.

A prompt is an artifact with an id, semver, owner, and schema — reviewed like code and pinned in
agent cards so an eval run always knows which prompt produced which score.
"""

from agentplatform.prompts.registry import PromptPack, PromptSpec, load_pack

__all__ = ["PromptPack", "PromptSpec", "load_pack"]
