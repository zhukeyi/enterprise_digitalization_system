"""SQL Safety Validator.

M3-T3: SQL injection prevention and read-only enforcement.

Checks:
- Blocked keywords: DELETE, UPDATE, DROP, TRUNCATE, INSERT, ALTER, CREATE, GRANT, REVOKE
- Multiple statements (semicolons in non-string context)
- Comment injection (-- and /* */)
- Dangerous system function calls (pg_sleep, etc.)
- Non-SELECT statements
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

# ══════════════════════════════════════════════════════════════════
# Safety Check Result
# ══════════════════════════════════════════════════════════════════


class SafetyCheckResult(BaseModel):
    """Result of SQL safety validation."""

    is_safe: bool = True
    violations: list[str] = Field(default_factory=list)
    sql: str = ""


# ══════════════════════════════════════════════════════════════════
# Blocked Keywords and Patterns
# ══════════════════════════════════════════════════════════════════

# Keywords that modify data or schema — strictly forbidden
BLOCKED_KEYWORDS: frozenset[str] = frozenset(
    {
        "DELETE",
        "UPDATE",
        "DROP",
        "TRUNCATE",
        "INSERT",
        "ALTER",
        "CREATE",
        "GRANT",
        "REVOKE",
        "MERGE",
        "REPLACE",
        "RENAME",
        "ATTACH",
        "DETACH",
        "VACUUM",
        "ANALYZE",  # SQL command, not the agent
        "REINDEX",
        "CLUSTER",
        "COPY",
        "CALL",
        "EXEC",
        "EXECUTE",
    }
)

# Dangerous function calls (patterns are uppercase because SQL is upper-cased before matching)
BLOCKED_FUNCTIONS: list[str] = [
    r"PG_SLEEP\s*\(",
    r"PG_TERMINATE_BACKEND\s*\(",
    r"LO_IMPORT\s*\(",
    r"LO_EXPORT\s*\(",
    r"PG_READ_FILE\s*\(",
    r"PG_LS_DIR\s*\(",
    r"PG_STAT_FILE\s*\(",
]

# Comment patterns that can be used for injection
COMMENT_PATTERNS: list[str] = [
    r"--",  # Single-line comment
    r"/\*",  # Multi-line comment start
    r"\*/",  # Multi-line comment end
]

# Valid statement types (case-insensitive)
ALLOWED_STATEMENTS: frozenset[str] = frozenset({"SELECT", "WITH"})


# ══════════════════════════════════════════════════════════════════
# SQL Safety Validator
# ══════════════════════════════════════════════════════════════════


class SQLSafetyValidator:
    """Validates SQL statements for safety (read-only, no injection).

    This validator enforces a strict read-only policy: only SELECT and
    WITH (CTE) statements are allowed. All DML/DDL statements and
    common SQL injection patterns are blocked.
    """

    def validate(self, sql: str) -> SafetyCheckResult:
        """Validate a SQL statement for safety.

        Args:
            sql: The SQL statement to validate.

        Returns:
            SafetyCheckResult with is_safe=True if the SQL passes all checks,
            or is_safe=False with a list of violations.
        """
        violations: list[str] = []

        # Normalize: strip whitespace
        sql_stripped = sql.strip()
        if not sql_stripped:
            violations.append("Empty SQL statement")
            return SafetyCheckResult(is_safe=False, violations=violations, sql=sql)

        # Upper-case copy for keyword matching (preserve original for output)
        sql_upper = sql_stripped.upper()

        # ── Check 1: Multi-statement detection (semicolons) ──
        # A single trailing semicolon is allowed; multiple semicolons are not.
        # We strip string literals first to avoid false positives from semicolons
        # inside quoted values.
        sql_no_strings = _strip_string_literals(sql_upper)
        semicolon_count = sql_no_strings.count(";")
        if semicolon_count > 1:
            violations.append(
                f"Multiple statements detected ({semicolon_count} semicolons) — "
                "only a single statement is allowed"
            )
        elif semicolon_count == 1 and not sql_stripped.rstrip().endswith(";"):
            # Semicolon in the middle (not at end) — likely multi-statement
            violations.append(
                "Semicolon detected mid-statement — possible multi-statement injection"
            )

        # ── Check 2: Comment injection ──
        for pattern in COMMENT_PATTERNS:
            if re.search(pattern, sql_no_strings):
                violations.append(
                    f"SQL comment pattern '{pattern}' detected — " "comments are not allowed"
                )

        # ── Check 3: Blocked keywords ──
        # Tokenize to avoid substring false positives (e.g., "updated_at" column)
        tokens = _tokenize_sql(sql_no_strings)
        for token in tokens:
            if token in BLOCKED_KEYWORDS:
                violations.append(
                    f"Blocked keyword '{token}' detected — only read-only queries are allowed"
                )

        # ── Check 4: Blocked functions ──
        for pattern in BLOCKED_FUNCTIONS:
            if re.search(pattern, sql_no_strings):
                violations.append(
                    "Blocked function call detected — system function access is not allowed"
                )

        # ── Check 5: Must start with SELECT or WITH ──
        if not violations:
            first_token = tokens[0] if tokens else ""
            if first_token not in ALLOWED_STATEMENTS:
                violations.append(
                    f"Statement must start with SELECT or WITH — "
                    f"found '{first_token or '(empty)'}'"
                )

        is_safe = len(violations) == 0
        return SafetyCheckResult(is_safe=is_safe, violations=violations, sql=sql)


# ══════════════════════════════════════════════════════════════════
# Internal Helpers
# ══════════════════════════════════════════════════════════════════


def _strip_string_literals(sql: str) -> str:
    """Remove single-quoted and double-quoted string literals from SQL.

    This prevents false positives when keywords appear inside string values
    (e.g., SELECT * FROM logs WHERE message = 'DELETE FROM users').
    """
    # Remove single-quoted strings ('...')
    result = re.sub(r"'(?:[^']|'')*'", "''", sql)
    # Remove double-quoted identifiers ("...")
    result = re.sub(r'"(?:[^"]|"")*"', '""', result)
    return result


def _tokenize_sql(sql: str) -> list[str]:
    """Tokenize SQL into whitespace-delimited tokens for keyword matching.

    This is a simple tokenizer that splits on word boundaries, ensuring that
    column names like "updated_at" or "deleted_flag" don't trigger keyword
    detection for "UPDATE" or "DELETE".
    """
    # Split on non-word characters, keeping only actual word tokens
    tokens = re.findall(r"\b[A-Za-z_]+\b", sql)
    return [t.upper() for t in tokens]


# ══════════════════════════════════════════════════════════════════
# Module-level singleton
# ══════════════════════════════════════════════════════════════════

_validator: SQLSafetyValidator | None = None


def get_validator() -> SQLSafetyValidator:
    """Get the singleton SQLSafetyValidator instance."""
    global _validator
    if _validator is None:
        _validator = SQLSafetyValidator()
    return _validator


def validate_sql(sql: str) -> SafetyCheckResult:
    """Convenience function: validate SQL using the singleton validator."""
    return get_validator().validate(sql)
