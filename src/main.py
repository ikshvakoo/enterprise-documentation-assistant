import argparse
import json
import sys
from pathlib import Path

from config import DATA_DIR
from config import DEFAULT_CHUNK_OVERLAP
from config import DEFAULT_CHUNK_WORDS
from config import DEFAULT_TOP_K
from config import INDEX_PATH
from corpus_summary import build_corpus_summary
from corpus_summary import format_corpus_summary
from evaluation import evaluate_retrieval
from evaluation import load_questions
from evaluation import result_to_text
from export import write_markdown
from export import write_release_notes_docx
from generation import generate_release_notes_for_selection
from generation import parse_issue_keys
from generator import format_citation
from generator import generate_answer
from generator import generate_release_notes
from models import SearchFilters
from retrieval import SearchService
from text_utils import truncate


def build_index(args: argparse.Namespace) -> int:
    """CLI handler that rebuilds the local BM25 index from source data."""
    service = SearchService.build(
        data_dir=DATA_DIR,
        index_path=INDEX_PATH,
        chunk_words=args.chunk_words,
        chunk_overlap=args.chunk_overlap,
    )
    counts = getattr(service, "last_build_counts", {})
    print(f"Loaded documents: {counts.get('documents', 0)}")
    print(f"Indexed chunks: {counts.get('chunks', len(service.index.chunks))}")
    print(f"Index written to: {INDEX_PATH}")
    return 0


def ensure_service() -> SearchService:
    """Load the search service, building the index automatically if needed."""
    return SearchService.load_or_build(DATA_DIR, INDEX_PATH)


def search(args: argparse.Namespace) -> int:
    """CLI handler for ranked retrieval over the indexed corpus."""
    service = ensure_service()
    results = service.search(args.query, top_k=args.top_k, filters=make_filters(args))
    if not results:
        print("No matching results found.")
        return 0

    for number, result in enumerate(results, start=1):
        print(f"{number}. score={result.score:.3f} {format_citation(result, number)}")
        print(f"   {truncate(result.chunk.text, args.max_chars)}")
        print()
    return 0


def answer(args: argparse.Namespace) -> int:
    """CLI handler that prints a citation-backed extractive answer."""
    service = ensure_service()
    results = service.search(args.query, top_k=args.top_k * 5, filters=make_filters(args))
    print(generate_answer(args.query, results))
    return 0


def release_notes(args: argparse.Namespace) -> int:
    """CLI handler that drafts baseline release-note bullets from retrieval results."""
    service = ensure_service()
    results = service.search(args.query, top_k=args.top_k * 4, filters=make_filters(args))
    print(generate_release_notes(results))
    return 0


def generate_release_notes_command(args: argparse.Namespace) -> int:
    """CLI handler that creates a structured release-note draft and exports it."""
    service = ensure_service()
    issue_keys = parse_issue_keys(args.issue_key, args.issue_keys_file)
    draft = generate_release_notes_for_selection(
        service=service,
        fix_version=args.fix_version,
        issue_keys=issue_keys,
        query=args.query,
        max_tickets=args.max_tickets,
    )

    if args.output_md:
        write_markdown(draft.markdown, args.output_md)
        print(f"Markdown release notes written to: {args.output_md}")
    if args.output_docx:
        write_release_notes_docx(draft.markdown, args.output_docx)
        print(f"DOCX release notes written to: {args.output_docx}")
    if not args.output_md and not args.output_docx:
        print(draft.markdown)

    print(f"\nTickets included: {len(draft.tickets)}")
    return 0


def stats(_: argparse.Namespace) -> int:
    """CLI handler that summarizes the saved index contents."""
    service = ensure_service()
    by_type = service.source_counts()
    print(f"Index: {INDEX_PATH}")
    print(f"Chunks: {len(service.index.chunks)}")
    for source_type, count in sorted(by_type.items()):
        print(f"- {source_type}: {count}")
    return 0


def corpus_summary(args: argparse.Namespace) -> int:
    """CLI handler that summarizes the local anonymized source dataset."""
    summary = build_corpus_summary(DATA_DIR)
    print(format_corpus_summary(summary))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(summary.to_dict(), handle, ensure_ascii=False, indent=2)
        print(f"\nSummary JSON written to: {args.output}")
    return 0


def release_tickets(args: argparse.Namespace) -> int:
    """CLI handler that lists Jira issues tied to a selected fix version."""
    service = ensure_service()
    issues = service.jira_issues_for_fix_version(args.fix_version)
    if not issues:
        print(f"No Jira issues found for fix version: {args.fix_version}")
        return 0

    print(f"Jira issues for fix version {args.fix_version}: {len(issues)}")
    for issue in issues[: args.limit]:
        components = ", ".join(str(value) for value in issue.get("components", []) if value)
        print(
            f"- {issue['issue_key']} | {issue.get('issue_type')} | "
            f"{issue.get('status')} | {components} | {truncate(str(issue.get('title', '')), 120)}"
        )
    if len(issues) > args.limit:
        print(f"... showing {args.limit} of {len(issues)}. Use --limit to show more.")
    return 0


def eval_retrieval(args: argparse.Namespace) -> int:
    """CLI handler that evaluates retrieval quality against a question set."""
    service = ensure_service()
    questions = load_questions(args.questions)
    result = evaluate_retrieval(service, questions, top_k=args.top_k, filters=make_filters(args))
    print(result_to_text(result))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(result.__dict__, handle, ensure_ascii=False, indent=2)
        print(f"\nDetailed results written to: {args.output}")
    return 0


def make_parser() -> argparse.ArgumentParser:
    """Build the command-line parser and register all subcommands."""
    parser = argparse.ArgumentParser(description="Enterprise documentation assistant prototype")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build-index", help="Load source files and build the local retrieval index")
    build.add_argument("--chunk-words", type=int, default=DEFAULT_CHUNK_WORDS)
    build.add_argument("--chunk-overlap", type=int, default=DEFAULT_CHUNK_OVERLAP)
    build.set_defaults(func=build_index)

    search_parser = subparsers.add_parser("search", help="Search the indexed corpus")
    add_query_args(search_parser)
    search_parser.add_argument("--max-chars", type=int, default=360)
    search_parser.set_defaults(func=search)

    answer_parser = subparsers.add_parser("answer", help="Create a grounded extractive answer with citations")
    add_query_args(answer_parser)
    answer_parser.set_defaults(func=answer)

    notes_parser = subparsers.add_parser("release-notes", help="Draft release-note bullets from retrieved context")
    add_query_args(notes_parser)
    notes_parser.set_defaults(func=release_notes)

    generate_notes_parser = subparsers.add_parser(
        "generate-release-notes",
        help="Generate structured release notes from selected Jira tickets",
    )
    generate_notes_parser.add_argument("--fix-version", help="Select Jira tickets by fix version")
    generate_notes_parser.add_argument(
        "--issue-key",
        action="append",
        help="Select one or more issue keys. Can be repeated or comma-separated.",
    )
    generate_notes_parser.add_argument("--issue-keys-file", type=Path, help="Text file containing one issue key per line")
    generate_notes_parser.add_argument("--query", help="Optional keyword query to narrow selected tickets")
    generate_notes_parser.add_argument("--max-tickets", type=int, default=40)
    generate_notes_parser.add_argument("--output-md", type=Path, help="Path for generated Markdown output")
    generate_notes_parser.add_argument("--output-docx", type=Path, help="Path for generated DOCX output")
    generate_notes_parser.set_defaults(func=generate_release_notes_command)

    release_tickets_parser = subparsers.add_parser(
        "release-tickets",
        help="List Jira tickets in the index for a fix version",
    )
    release_tickets_parser.add_argument("fix_version")
    release_tickets_parser.add_argument("--limit", type=int, default=25)
    release_tickets_parser.set_defaults(func=release_tickets)

    eval_parser = subparsers.add_parser(
        "eval-retrieval",
        help="Evaluate retrieval with a JSON question set",
    )
    eval_parser.add_argument("questions", type=Path, help="Path to retrieval question JSON file")
    eval_parser.add_argument("--top-k", type=int, default=10)
    eval_parser.add_argument("--output", type=Path, help="Optional path for detailed JSON results")
    add_filter_args(eval_parser)
    eval_parser.set_defaults(func=eval_retrieval)

    stats_parser = subparsers.add_parser("stats", help="Show index statistics")
    stats_parser.set_defaults(func=stats)

    corpus_parser = subparsers.add_parser(
        "corpus-summary",
        help="Summarize source dataset counts and date/version span",
    )
    corpus_parser.add_argument("--output", type=Path, help="Optional path for summary JSON")
    corpus_parser.set_defaults(func=corpus_summary)
    return parser


def add_query_args(parser: argparse.ArgumentParser) -> None:
    """Attach shared query and metadata-filter arguments to search-like commands."""
    parser.add_argument("query")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    add_filter_args(parser)


def add_filter_args(parser: argparse.ArgumentParser) -> None:
    """Attach shared metadata-filter arguments to a parser."""
    parser.add_argument(
        "--source-type",
        choices=["jira", "release_note", "test_case"],
        help="Restrict retrieval to one corpus type",
    )
    parser.add_argument("--issue-type", help="Restrict Jira results to one issue type")
    parser.add_argument("--status", help="Restrict Jira results to one status")
    parser.add_argument("--priority", help="Restrict Jira results to one priority")
    parser.add_argument("--component", help="Restrict Jira results to one component")
    parser.add_argument("--fix-version", help="Restrict Jira results to one fix version")
    parser.add_argument("--issue-key", help="Restrict results to one issue key")


def make_filters(args: argparse.Namespace) -> SearchFilters:
    """Convert parsed CLI arguments into a SearchFilters object."""
    filters = SearchFilters(
        source_type=getattr(args, "source_type", None),
        issue_type=getattr(args, "issue_type", None),
        status=getattr(args, "status", None),
        priority=getattr(args, "priority", None),
        component=getattr(args, "component", None),
        fix_version=getattr(args, "fix_version", None),
        issue_key=getattr(args, "issue_key", None),
    )
    return filters if filters.has_filters() else SearchFilters()


def main(argv: list[str] | None = None) -> int:
    """Program entry point used by both direct execution and tests."""
    configure_output()
    parser = make_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def configure_output() -> None:
    """Force UTF-8 console output so extracted document symbols do not crash on Windows."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    sys.exit(main())
