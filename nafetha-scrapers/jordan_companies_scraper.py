import argparse
import asyncio

from app.services.scrape_runner import run_scrape_job


async def _run_from_cli(args: argparse.Namespace) -> None:
    async def update_progress(**kwargs) -> None:
        message = kwargs.get("last_message")
        if message:
            print(f"[progress] {message}")

    outputs = await run_scrape_job(
        keywords=args.keywords,
        locations=args.locations,
        jobs_per_location=args.jobs_per_location,
        delay_seconds=args.delay_s,
        session_path=args.session,
        output_dir=args.output_dir,
        verbose=args.verbose,
        progress_updater=update_progress,
        is_cancel_requested=lambda: False,
    )
    print(f"\nSaved jobs to: {outputs.jobs_xlsx}")
    print(f"Saved companies to: {outputs.companies_xlsx}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape LinkedIn jobs and companies into XLSX files.")
    parser.add_argument("--keywords", default="", help="Job keywords to seed company discovery.")
    parser.add_argument(
        "--locations",
        nargs="*",
        default=["Amman, Jordan"],
        help="LinkedIn job locations to search in.",
    )
    parser.add_argument("--jobs-per-location", type=int, default=200)
    parser.add_argument("--delay-s", type=float, default=2.0)
    parser.add_argument("--session", default="session.json")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    asyncio.run(_run_from_cli(args))


if __name__ == "__main__":
    main()

