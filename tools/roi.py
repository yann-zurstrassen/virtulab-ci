#!/usr/bin/env python3
"""Hours of bench waiting avoided per week, from inputs you supply.

hours_saved = devs x prs_per_dev_per_day x days_per_week x bench_wait_hours x rerun_rate x caught_share

Every input is an assumption about YOUR team. This script does arithmetic; it measures nothing.
"""
import argparse
import sys


def positive(value: str) -> float:
    number = float(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be zero or positive")
    return number


def fraction(value: str) -> float:
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise argparse.ArgumentTypeError("must be between 0 and 1")
    return number


def hours_saved_per_week(devs: float, prs_per_day: float, wait_hours: float, rerun_rate: float,
                         days: float, caught_share: float) -> float:
    return devs * prs_per_day * days * wait_hours * rerun_rate * caught_share


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--devs", type=positive, required=True, help="firmware developers")
    parser.add_argument("--prs-per-day", type=positive, required=True,
                        help="PRs each developer opens per working day")
    parser.add_argument("--bench-wait-hours", type=positive, required=True,
                        help="average wait for a bench run per PR, in hours")
    parser.add_argument("--rerun-rate", type=fraction, required=True,
                        help="share of PRs that need an extra bench run (0 to 1)")
    parser.add_argument("--days-per-week", type=positive, default=5.0, help="working days (default 5)")
    parser.add_argument("--caught-share", type=fraction, default=1.0,
                        help="share of those reruns emulation would catch earlier (default 1.0, an "
                             "upper bound: lower it to what you can justify)")
    args = parser.parse_args()

    hours = hours_saved_per_week(args.devs, args.prs_per_day, args.bench_wait_hours,
                                 args.rerun_rate, args.days_per_week, args.caught_share)
    print("ASSUMPTIONS (yours, not measured):")
    print(f"  developers            {args.devs:g}")
    print(f"  PRs / dev / day       {args.prs_per_day:g}")
    print(f"  working days / week   {args.days_per_week:g}")
    print(f"  avg bench wait (h)    {args.bench_wait_hours:g}")
    print(f"  rerun rate            {args.rerun_rate:g}")
    print(f"  caught-share          {args.caught_share:g}")
    print(f"hours saved per week: {hours:.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
