import json
from pathlib import Path
from typing import Any

from models import SourceDocument
from text_utils import clean_text
from text_utils import join_nonempty


def load_jira_export(path: Path) -> list[SourceDocument]:
    """Parse the anonymized Jira JSON export into normalized SourceDocument objects."""
    with path.open("r", encoding="utf-8") as handle:
        issues = json.load(handle)

    documents: list[SourceDocument] = []
    for issue in issues:
        fields = issue.get("fields", {})
        key = clean_text(issue.get("key"))
        summary = clean_text(fields.get("summary"))

        # Jira comments and descriptions may be plain strings or Atlassian
        # Document Format objects, so all rich text goes through extract_adf_text.
        comments = fields.get("comment", {}).get("comments", [])
        comment_text = [extract_adf_text(comment.get("body")) for comment in comments]

        # Store list-valued fields as lists so later retrieval can filter by
        # component or fix version without reparsing display text.
        fix_versions = [
            clean_text(version.get("name"))
            for version in fields.get("fixVersions", [])
            if isinstance(version, dict)
        ]
        components = [
            clean_text(component.get("name"))
            for component in fields.get("components", [])
            if isinstance(component, dict)
        ]

        body = join_nonempty(
            [
                # The body intentionally repeats metadata in readable text so
                # BM25 can match queries against fields like status or priority.
                f"Issue Key: {key}",
                f"Summary: {summary}",
                f"Issue Type: {nested_name(fields.get('issuetype'))}",
                f"Status: {nested_name(fields.get('status'))}",
                f"Priority: {nested_name(fields.get('priority'))}",
                f"Components: {', '.join(filter(None, components))}",
                f"Fix Versions: {', '.join(filter(None, fix_versions))}",
                f"Created: {clean_text(fields.get('created'))}",
                f"Resolved: {clean_text(fields.get('resolutiondate'))}",
                "Description:\n" + extract_adf_text(fields.get("description")),
                "Comments:\n" + join_nonempty(comment_text),
            ]
        )

        documents.append(
            SourceDocument(
                doc_id=f"jira:{key or issue.get('id')}",
                source_type="jira",
                title=summary or key,
                body=body,
                source_path=str(path),
                metadata={
                    "issue_key": key,
                    "status": nested_name(fields.get("status")),
                    "issue_type": nested_name(fields.get("issuetype")),
                    "priority": nested_name(fields.get("priority")),
                    "components": components,
                    "fix_versions": fix_versions,
                    "created": clean_text(fields.get("created")),
                    "resolved": clean_text(fields.get("resolutiondate")),
                },
            )
        )

    return documents


def nested_name(value: Any) -> str:
    """Extract a Jira nested object's display name, or clean a simple value."""
    if isinstance(value, dict):
        return clean_text(value.get("name"))
    return clean_text(value)


def extract_adf_text(value: Any) -> str:
    """Recursively extract readable text from Atlassian Document Format values.

    Jira rich-text fields may contain nested dictionaries/lists instead of plain
    strings. This function walks those nested structures and collects all text
    nodes into one normalized string.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, list):
        return join_nonempty(extract_adf_text(item) for item in value)
    if not isinstance(value, dict):
        return clean_text(value)

    parts = []
    if "text" in value:
        parts.append(clean_text(value.get("text")))
    # ADF stores child nodes under "content". We intentionally skip "attrs"
    # dictionaries because they usually contain IDs/metadata rather than prose.
    for child_key in ("content", "attrs"):
        child = value.get(child_key)
        if child_key == "attrs" and isinstance(child, dict):
            continue
        parts.append(extract_adf_text(child))
    return join_nonempty(parts, " ")
