import re

# Matches {{ variable_name }}. Allows letters, digits, underscores, dashes, dots,
# AND internal spaces (e.g. {{Word Count}}, {{Tone of Voice}}). Outer whitespace
# inside the braces is stripped, and multiple internal spaces collapse to one,
# so {{ Word Count }} and {{Word  Count}} both resolve to "Word Count".
_VAR_PATTERN = re.compile(r"\{\{\s*([A-Za-z_][\w\.\- ]*?)\s*\}\}")
_WS_RUN = re.compile(r"\s+")


def _normalize(name: str) -> str:
    return _WS_RUN.sub(" ", name).strip()


def extract_variables(content: str) -> list[str]:
    """Return unique variable names in declaration order."""
    seen: set[str] = set()
    out: list[str] = []
    for match in _VAR_PATTERN.finditer(content):
        name = _normalize(match.group(1))
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def render_template(content: str, variables: dict[str, str]) -> tuple[str, list[str]]:
    """Substitute {{var}} placeholders with values.

    Returns (rendered_text, missing_var_names). Missing variables are left as
    their literal {{var}} in the output so the model still receives a valid prompt
    while the caller can warn the user.
    """
    missing: list[str] = []

    def repl(m: re.Match[str]) -> str:
        name = _normalize(m.group(1))
        if name in variables and variables[name] != "":
            return variables[name]
        if name and name not in missing:
            missing.append(name)
        return m.group(0)  # leave the placeholder as-is

    rendered = _VAR_PATTERN.sub(repl, content)
    return rendered, missing
