"""9-pass replacer chain (inspired by OpenCode's edit.ts)."""

import re
from difflib import SequenceMatcher
from typing import Optional


def _similarity(a: str, b: str) -> float:
    """Compute Levenshtein-like similarity ratio between two strings."""
    return SequenceMatcher(None, a, b).ratio()


def _normalize_line_endings(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")


def _extract_actual_lines(original_lines: list[str], start: int, count: int) -> str:
    """Extract *count* lines from original starting at *start*, joined with newline."""
    end = min(start + count, len(original_lines))
    return "\n".join(original_lines[start:end])


class _Replacer:
    """Base class for a single replacer strategy."""

    name: str = "base"

    def find(self, original: str, old_content: str) -> Optional[str]:
        """Return the actual substring in *original* that matches *old_content*, or None."""
        raise NotImplementedError


class _SimpleReplacer(_Replacer):
    """Pass 1: exact string match."""

    name = "simple"

    def find(self, original: str, old_content: str) -> Optional[str]:
        if old_content in original:
            return old_content
        return None


class _LineTrimmedReplacer(_Replacer):
    """Pass 2: match with each line trimmed (preserve original indentation)."""

    name = "line_trimmed"

    def find(self, original: str, old_content: str) -> Optional[str]:
        old_lines = [ln.strip() for ln in old_content.split("\n")]
        if not old_lines or not any(old_lines):
            return None

        original_lines = original.split("\n")

        for i, line in enumerate(original_lines):
            if line.strip() == old_lines[0]:
                if i + len(old_lines) > len(original_lines):
                    continue
                match = True
                for j, old_ln in enumerate(old_lines):
                    if original_lines[i + j].strip() != old_ln:
                        match = False
                        break
                if match:
                    actual = "\n".join(original_lines[i : i + len(old_lines)])
                    if actual in original:
                        return actual
        return None


class _BlockAnchorReplacer(_Replacer):
    """Pass 3: first/last lines must match exactly (trimmed); middle lines use similarity."""

    name = "block_anchor"
    THRESHOLD_SINGLE = 0.0
    THRESHOLD_MULTI = 0.3

    def find(self, original: str, old_content: str) -> Optional[str]:
        old_lines = old_content.split("\n")
        if len(old_lines) < 3:
            return None  # Need at least first, middle, last

        first_trimmed = old_lines[0].strip()
        last_trimmed = old_lines[-1].strip()
        middle_old = [ln.strip() for ln in old_lines[1:-1]]

        original_lines = original.split("\n")
        candidates: list[tuple[int, float]] = []  # (start_index, avg_similarity)

        for i, line in enumerate(original_lines):
            if line.strip() != first_trimmed:
                continue
            # Search for matching last line within a reasonable window
            window_end = min(i + len(old_lines) * 2, len(original_lines))
            for end_idx in range(i + len(old_lines) - 1, window_end):
                if end_idx >= len(original_lines):
                    break
                if original_lines[end_idx].strip() != last_trimmed:
                    continue
                # Check middle lines similarity
                middle_orig = [ln.strip() for ln in original_lines[i + 1 : end_idx]]
                if not middle_old and not middle_orig:
                    candidates.append((i, 1.0))
                    continue
                if not middle_old or not middle_orig:
                    continue
                sim = _similarity("\n".join(middle_old), "\n".join(middle_orig))
                candidates.append((i, sim))

        if not candidates:
            return None

        threshold = self.THRESHOLD_SINGLE if len(candidates) == 1 else self.THRESHOLD_MULTI
        # Pick best candidate above threshold
        best = max(candidates, key=lambda c: c[1])
        if best[1] < threshold:
            return None

        start = best[0]
        # Find the end index again for the best match
        for end_idx in range(
            start + len(old_lines) - 1,
            min(start + len(old_lines) * 2, len(original_lines)),
        ):
            if end_idx >= len(original_lines):
                break
            if original_lines[end_idx].strip() == last_trimmed:
                actual = "\n".join(original_lines[start : end_idx + 1])
                if actual in original:
                    return actual
        return None


class _WhitespaceNormalizedReplacer(_Replacer):
    """Pass 4: normalize all whitespace (collapse runs, strip lines)."""

    name = "whitespace_normalized"

    def _normalize(self, s: str) -> str:
        lines = s.split("\n")
        return "\n".join(re.sub(r"\s+", " ", ln).strip() for ln in lines)

    def find(self, original: str, old_content: str) -> Optional[str]:
        norm_old = self._normalize(old_content)
        original_lines = original.split("\n")
        old_line_count = len(old_content.split("\n"))

        for i in range(len(original_lines)):
            end = min(i + old_line_count + 2, len(original_lines))
            for j in range(i + old_line_count - 1, end + 1):
                if j > len(original_lines):
                    break
                candidate = "\n".join(original_lines[i:j])
                if self._normalize(candidate) == norm_old:
                    if candidate in original:
                        return candidate
        return None


class _IndentationFlexibleReplacer(_Replacer):
    """Pass 5: ignore indentation differences entirely."""

    name = "indentation_flexible"

    def find(self, original: str, old_content: str) -> Optional[str]:
        old_stripped = [ln.strip() for ln in old_content.split("\n") if ln.strip()]
        if not old_stripped:
            return None

        original_lines = original.split("\n")

        for i, line in enumerate(original_lines):
            if line.strip() != old_stripped[0]:
                continue
            # Try to match all stripped lines, skipping blank original lines
            matched_indices: list[int] = []
            j = 0
            for k in range(i, min(i + len(old_stripped) * 3, len(original_lines))):
                if j >= len(old_stripped):
                    break
                if not original_lines[k].strip():
                    continue  # Skip blank lines in original
                if original_lines[k].strip() == old_stripped[j]:
                    matched_indices.append(k)
                    j += 1
                else:
                    break

            if j == len(old_stripped) and matched_indices:
                start = matched_indices[0]
                end = matched_indices[-1] + 1
                actual = "\n".join(original_lines[start:end])
                if actual in original:
                    return actual
        return None


class _EscapeNormalizedReplacer(_Replacer):
    """Pass 6: unescape common escape sequences before matching."""

    name = "escape_normalized"

    _ESCAPES = {r"\\n": "\n", r"\\t": "\t", r"\\\\": "\\", r"\\\"": '"', r"\\'": "'"}

    def _unescape(self, s: str) -> str:
        result = s
        for escaped, unescaped in self._ESCAPES.items():
            result = result.replace(escaped, unescaped)
        return result

    def find(self, original: str, old_content: str) -> Optional[str]:
        unescaped = self._unescape(old_content)
        if unescaped == old_content:
            return None  # No escapes to normalize
        if unescaped in original:
            return unescaped
        return None


class _TrimmedBoundaryReplacer(_Replacer):
    """Pass 7: find trimmed boundaries and expand to full lines."""

    name = "trimmed_boundary"

    def find(self, original: str, old_content: str) -> Optional[str]:
        trimmed = old_content.strip()
        if trimmed == old_content:
            return None  # Nothing to trim

        if trimmed in original:
            return trimmed

        # Try line-level boundary expansion
        old_lines = old_content.split("\n")
        first_content = old_lines[0].strip()
        last_content = old_lines[-1].strip()

        if not first_content or not last_content:
            return None

        original_lines = original.split("\n")
        for i, line in enumerate(original_lines):
            if first_content not in line:
                continue
            end = min(i + len(old_lines) + 2, len(original_lines))
            for j in range(i + 1, end):
                if j >= len(original_lines):
                    break
                if last_content not in original_lines[j]:
                    continue
                candidate = "\n".join(original_lines[i : j + 1])
                if candidate in original:
                    return candidate
        return None


class _ContextAwareReplacer(_Replacer):
    """Pass 8: use surrounding context blocks for matching."""

    name = "context_aware"

    def find(self, original: str, old_content: str) -> Optional[str]:
        old_lines = old_content.split("\n")
        if len(old_lines) < 2:
            return None

        original_lines = original.split("\n")

        # Use first and last non-empty lines as context anchors
        first_ctx = next((ln.strip() for ln in old_lines if ln.strip()), None)
        last_ctx = next((ln.strip() for ln in reversed(old_lines) if ln.strip()), None)
        if not first_ctx or not last_ctx:
            return None

        # Find all positions of first anchor
        starts: list[int] = []
        for i, line in enumerate(original_lines):
            if first_ctx in line.strip():
                starts.append(i)

        if not starts:
            return None

        best_match: Optional[str] = None
        best_sim = 0.0

        for start in starts:
            # Search for end anchor
            for end in range(
                start + 1, min(start + len(old_lines) * 2, len(original_lines))
            ):
                if last_ctx in original_lines[end].strip():
                    candidate = "\n".join(original_lines[start : end + 1])
                    sim = _similarity(old_content.strip(), candidate.strip())
                    if sim > best_sim and sim > 0.5:
                        best_sim = sim
                        best_match = candidate
                    break  # Only check first end anchor per start

        if best_match and best_match in original:
            return best_match
        return None


class _MultiOccurrenceReplacer(_Replacer):
    """Pass 9: find all exact matches when there are multiple (for match_all mode)."""

    name = "multi_occurrence"

    def find(self, original: str, old_content: str) -> Optional[str]:
        # This pass is a last-resort that tries trimmed exact match
        trimmed = old_content.strip()
        if not trimmed:
            return None

        # Find the trimmed content in original lines
        original_lines = original.split("\n")
        trimmed_lines = trimmed.split("\n")

        for i in range(len(original_lines) - len(trimmed_lines) + 1):
            candidate_lines = original_lines[i : i + len(trimmed_lines)]
            if all(
                a.strip() == b.strip() for a, b in zip(candidate_lines, trimmed_lines)
            ):
                candidate = "\n".join(candidate_lines)
                if candidate in original:
                    return candidate
        return None


# Ordered chain of replacers (tried in sequence)
_REPLACER_CHAIN: list[_Replacer] = [
    _SimpleReplacer(),
    _LineTrimmedReplacer(),
    _BlockAnchorReplacer(),
    _WhitespaceNormalizedReplacer(),
    _IndentationFlexibleReplacer(),
    _EscapeNormalizedReplacer(),
    _TrimmedBoundaryReplacer(),
    _ContextAwareReplacer(),
    _MultiOccurrenceReplacer(),
]
