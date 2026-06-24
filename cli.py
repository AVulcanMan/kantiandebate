#!/usr/bin/env python3
"""KDS command-line entrypoint.

Phase 0 implements `ingest`. Pipeline/drill/generate commands are stubbed and
land in later phases. Uses stdlib argparse so the CLI has no extra dependencies.
"""

from __future__ import annotations

import argparse
import sys


def cmd_ingest(args: argparse.Namespace) -> int:
    from kds.corpus.ingest import build_corpus

    stats = build_corpus()
    print(
        f"Wrote {stats['unique_written']:,} unique resolutions "
        f"(from {stats['rows_seen']:,} rows) to {stats['db_path']}"
    )
    print("By class:", stats["by_class"])
    return 0


def cmd_transcript_check(args: argparse.Namespace) -> int:
    from kds.pipeline.transcript_io import load_transcript

    t = load_transcript(args.path)
    print(f"OK: {len(t.segments)} segments parsed from {args.path}")
    if t.metadata and t.metadata.title:
        print(f"Title: {t.metadata.title}")
    return 0


def cmd_pipeline_run(args: argparse.Namespace) -> int:
    from kds.pipeline.run import run_pipeline

    result = run_pipeline(args.url)
    print(f"\n=== {result['title']} ({result['video_id']}) ===")
    print(
        f"{result['n_segments']} transcript segments -> "
        f"{result['n_arguments']} arguments "
        f"({result['n_needs_review']} need review)\n"
    )
    for a in result["arguments"]:
        flag = "  [REVIEW]" if a.needs_review else ""
        print(f"{a.order}. [{a.speaker or '?'}] {a.claim}{flag}")
    print(f"\nReady. Drill with: python cli.py drill refutation --video {result['video_id']} --arg 1")
    return 0


def _read_multiline(prompt: str) -> str:
    print(prompt + " (end with an empty line):")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if not line.strip():
            break
        lines.append(line)
    return "\n".join(lines)


def cmd_drill(args: argparse.Namespace) -> int:
    from kds import store
    from kds.generators.flowing import FlowingDrill
    from kds.generators.refutation import RefutationDrill
    from kds.generators.round_vision import QUESTIONS, RoundVisionDrill

    arguments = store.load_arguments(args.video)
    if not arguments:
        print(f"No flow stored for {args.video!r}. Run `pipeline run` first.")
        return 1
    by_ord = {a.order: a for a in arguments}

    if args.kind == "flowing":
        flow = _read_multiline("\nFlow this round — list the arguments you caught")
        if not flow.strip():
            print("No flow entered.")
            return 1
        res = FlowingDrill().grade(arguments, flow)
        print(f"\nCoverage: {res.coverage_score}")
        print(f"Caught ({len(res.caught)}): " + "; ".join(res.caught[:5]))
        print(f"Missed ({len(res.missed)}): " + "; ".join(res.missed[:8]))
        if res.notes:
            print(f"\nNotes: {res.notes}")
        store.save_run("flowing", args.video, None, flow, res.model_dump())
        return 0

    if args.kind == "round_vision":
        rv = RoundVisionDrill()
        before, after = rv.split_snapshot(arguments)
        print(rv.build_prompt(before))
        answers = {}
        for key in QUESTIONS:
            try:
                answers[key] = input(f"\n{key}: ").strip()
            except EOFError:
                answers[key] = ""
        res = rv.grade(before, after, answers)
        print(f"\nScore: {res.score}")
        for k, v in res.per_question_grade.items():
            print(f"  {k}: {v}")
        print(f"\nWhat actually happened next:\n{res.reveal}")
        store.save_run("round_vision", args.video, None, str(answers), res.model_dump())
        return 0

    if args.kind == "refutation":
        arg = by_ord.get(args.arg)
        if not arg:
            print(f"No argument #{args.arg} for {args.video}.")
            return 1
        drill = RefutationDrill()
        prompt = drill.drill(arg)
        print(f"\nREFUTE THIS:\n{prompt.prompt}")
        if prompt.hints:
            print("\nHints:")
            for h in prompt.hints:
                print(f"  - {h}")
        # Non-interactive: pass --refutation "..." to skip the prompt entirely.
        if args.refutation:
            user_ref = args.refutation.strip()
            print(f"\nYour refutation:\n> {user_ref}")
        else:
            try:
                user_ref = input("\nYour refutation (blank to skip grading):\n> ").strip()
            except EOFError:
                user_ref = ""
        if user_ref:
            grade = drill.grade(arg, user_ref)
            print(f"\nClash: {grade.clash_type} | Score: {grade.score}")
            print(f"Landed: {grade.what_landed}")
            print(f"Dropped: {grade.what_was_dropped}")
            print(f"\nModel refutation:\n{grade.model_refutation}")
            store.save_run("refutation", args.video, args.arg, user_ref, grade.model_dump())
        return 0

    print(f"Drill kind {args.kind!r} not wired in the CLI yet.")
    return 1


def cmd_generate(args: argparse.Namespace) -> int:
    if args.what != "motion":
        print(f"generate {args.what!r} not implemented.")
        return 1
    from kds.generators.motion import MotionGenerator

    motions = MotionGenerator().generate(
        args.type, n=args.n, theme=args.theme, use_news=args.news
    )
    label = args.type.upper()
    if args.theme:
        label += f" · theme: {args.theme}"
    if args.news or args.theme:
        label += " · news-grounded"
    print(f"\n=== {len(motions)} {label} motions ===\n")
    for i, m in enumerate(motions, 1):
        print(f"{i}. {m.motion}")
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    if args.what != "motion":
        print(f"eval {args.what!r} not implemented.")
        return 1
    from kds.eval import eval_motion

    print("Running motion eval (generate + judge per case, paced for rate limits)...")
    result = eval_motion()
    s = result["summary"]
    print(f"\n=== Motion eval over {s['n_motions']} motions ===")
    print(f"  type_accuracy: {s['type_accuracy']}")
    print(f"  specificity:   {s['specificity']} / 5")
    print(f"  debatability:  {s['debatability']} / 5")
    print(f"  COMPOSITE:     {s['composite']} / 10")
    print("\n  by type (specificity, type_accuracy):")
    for t, v in result["by_type"].items():
        print(f"    {t:7s}: spec {v['specificity']}/5, type_acc {v['type_accuracy']}")
    if args.verbose:
        print("\n  per-motion:")
        for m in result["motions"]:
            print(f"    [{m['composite']:.1f}] ({m['type']}) {m['motion'][:70]}  — {m['note']}")
    return 0


def cmd_caselist(args: argparse.Namespace) -> int:
    from kds.caselist import client
    from kds.caselist.search import search

    if args.caselist_cmd == "list":
        for c in client.list_caselists():
            print(f"  {c['name']:14s} {c.get('level',''):8s} event={c.get('event','')} year={c.get('year')}")
        return 0

    if args.caselist_cmd == "open":
        cite = client.get_cite_by_path(args.path)
        print(f"\n# {cite.get('title') or '(untitled)'}\n")
        print(cite.get("cites") or "(no cite text)")
        return 0

    if args.caselist_cmd == "download":
        p = client.download_file(args.path, args.dest)
        print(f"Saved {p} ({p.stat().st_size:,} bytes)")
        return 0

    if args.caselist_cmd == "grab":
        from kds.caselist.grab import grab

        print(f"Finding {args.n} file(s) matching {args.query!r} (confirming with LLM)...")
        res = grab(
            args.query, n=args.n, dest=args.dest, side=args.side, argtype=args.argtype,
            event=args.event, level=args.level, confirm=not args.no_confirm,
        )
        print(f"\nWant: {res['want']} | considered {res['considered']} candidates")
        for d in res["downloaded"]:
            why = f" — {d['why']}" if d.get("why") else ""
            print(f"  ✓ {d['team']}{why}\n    {d['file']}")
        for s in res["skipped"][:5]:
            print(f"  ✗ {s['team']}: {s['reason']}")
        if not res["downloaded"]:
            print("  (nothing downloaded)")
        return 0

    # search
    results = search(
        args.query,
        event=args.event,
        level=args.level,
        type=args.type,
        side=args.side,
        argtype=args.argtype,
        school=args.school,
        team=args.team,
        limit=args.limit,
        semantic=args.semantic,
    )
    if not results:
        print("No results.")
        return 0
    print(f"\n=== {len(results)} results for {args.query!r} ===\n")
    for i, r in enumerate(results, 1):
        side = f" [{r.side}]" if r.side else ""
        atypes = f" {{{','.join(r.argtypes)}}}" if r.argtypes else ""
        if r.semantic_score is not None:
            tag = f"sem {r.semantic_score:.0f}/10"
        else:
            tag = f"{r.score:.0f}"
        print(f"{i}. [{tag}] {r.team}{side}{atypes} · {r.type} · {r.caselist}")
        print(f"   {r.title[:90]}")
        if r.semantic_why:
            print(f"   ~ {r.semantic_why}")
        snip = " ".join(r.snippet.split())[:160]
        if snip:
            print(f"   {snip}")
        if r.url:
            print(f"   {r.url}")
        print()
    return 0


def _stub(name: str):
    def run(args: argparse.Namespace) -> int:
        print(f"`{name}` is not implemented yet (lands in a later phase).")
        return 1

    return run


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kds", description="Kantian Debate Society CLI")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("ingest", help="Build corpus.sqlite from the classified CSV").set_defaults(
        func=cmd_ingest
    )

    tc = sub.add_parser("transcript-check", help="Validate a transcript JSON file")
    tc.add_argument("path")
    tc.set_defaults(func=cmd_transcript_check)

    # pipeline run <url>
    pipe = sub.add_parser("pipeline", help="Footage pipeline")
    pipe_sub = pipe.add_subparsers(dest="pipeline_cmd", required=True)
    pr = pipe_sub.add_parser("run", help="YouTube URL -> drills")
    pr.add_argument("url")
    pr.set_defaults(func=cmd_pipeline_run)

    # drill <kind> --video <id> --arg <n>
    drill = sub.add_parser("drill", help="Run a drill")
    drill.add_argument("kind", choices=["refutation", "flowing", "round_vision"])
    drill.add_argument("--video", required=True)
    drill.add_argument("--arg", type=int, default=1)
    drill.add_argument(
        "--refutation",
        help="Your refutation text (non-interactive; refutation drill only)",
    )
    drill.set_defaults(func=cmd_drill)

    # generate motion --type value --theme "AI" --n 5 --news
    g = sub.add_parser("generate", help="Generate motions")
    g.add_argument("what", choices=["motion"])
    g.add_argument("--type", choices=["policy", "value", "fact"], required=True)
    g.add_argument("--theme", default=None, help="Optional topic to center motions on")
    g.add_argument("--n", type=int, default=5, help="How many motions")
    g.add_argument(
        "--news", action="store_true", help="Ground in recent news (auto-on if --theme set)"
    )
    g.set_defaults(func=cmd_generate)

    # eval motion [-v]
    ev = sub.add_parser("eval", help="Score generator quality against rubrics")
    ev.add_argument("what", choices=["motion"])
    ev.add_argument("-v", "--verbose", action="store_true", help="Show per-motion scores")
    ev.set_defaults(func=cmd_eval)

    # caselist search "query" [filters] | caselist list
    cl = sub.add_parser("caselist", help="Search the OpenCaseList disclosure wiki")
    cl_sub = cl.add_subparsers(dest="caselist_cmd", required=True)
    cl_sub.add_parser("list", help="List available caselists (shards)").set_defaults(func=cmd_caselist)
    cs = cl_sub.add_parser("search", help="Federated, ranked, filtered search")
    cs.add_argument("query")
    cs.add_argument("--event", choices=["cx", "ld", "pf"], help="cx=policy")
    cs.add_argument("--level", choices=["hs", "college"])
    cs.add_argument("--type", choices=["cite", "file"], help="disclosed cite vs full doc")
    cs.add_argument("--side", choices=["aff", "neg"])
    cs.add_argument(
        "--argtype",
        choices=["kritik", "counterplan", "topicality", "theory", "disad",
                 "advantage", "plan", "framework", "case"],
        help="filter by argument type",
    )
    cs.add_argument("--school", help="filter by school (substring)")
    cs.add_argument("--team", help="filter by team (substring)")
    cs.add_argument("--limit", type=int, default=25)
    cs.add_argument(
        "--semantic", action="store_true", help="LLM re-rank top results by meaning"
    )
    cs.set_defaults(func=cmd_caselist)
    co = cl_sub.add_parser("open", help="Print a cite's full text by its path")
    co.add_argument("path", help="e.g. ndtceda25/MissouriState/BaHa#653212")
    co.set_defaults(func=cmd_caselist)
    cd = cl_sub.add_parser("download", help="Download a disclosure file (.docx)")
    cd.add_argument("path", help="a file's download_path from search results")
    cd.add_argument("--dest", default="downloads", help="destination folder")
    cd.set_defaults(func=cmd_caselist)
    gr = cl_sub.add_parser("grab", help="Find + LLM-confirm + download in one shot")
    gr.add_argument("query")
    gr.add_argument("-n", type=int, default=3, help="how many files to download")
    gr.add_argument("--dest", default="downloads", help="destination folder")
    gr.add_argument("--side", choices=["aff", "neg"])
    gr.add_argument(
        "--argtype",
        choices=["kritik", "counterplan", "topicality", "theory", "disad",
                 "advantage", "plan", "framework", "case"],
    )
    gr.add_argument("--event", choices=["cx", "ld", "pf"])
    gr.add_argument("--level", choices=["hs", "college"])
    gr.add_argument("--no-confirm", action="store_true", help="skip LLM confirmation (keyword only)")
    gr.set_defaults(func=cmd_caselist)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
