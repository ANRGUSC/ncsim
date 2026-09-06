"""Explicit ns-3.41 packet reruns; never called by the Python study commands."""
import argparse
from pathlib import Path
import subprocess


def commands(suite, seed):
    common = [f'--seed={seed}']
    if suite == 'main':
        for n in range(1,9):
            yield 'main_contention', common + [f'--nLinks={n}', '--simTime=30']
        for sep in (10,20,30,40,50,60,65,70,72,75,80,90,100,120,150,200):
            yield 'main_separation', common + [f'--separation={sep}', '--simTime=30', '--idealMcs=false']
    elif suite == 'short_contention':
        for n in range(1,9):
            yield 'short_contention', common + [f'--nLinks={n}', '--simTime=5']
    elif suite == 'overlapping':
        yield 'overlapping', common + ['--simTime=5']
    elif suite == 'rate_overhead':
        for mcs in (0,11):
            for rts in (0,1):
                yield 'rate_overhead', common + ['--nLinks=1', f'--mcs={mcs}', f'--rts={rts}', '--simTime=5.5']
    elif suite == 'dynamic':
        for sep in (40,80):
            yield 'dynamic', common + [f'--separation={sep}']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('suite', choices=('main','short_contention','overlapping','rate_overhead','dynamic'))
    parser.add_argument('--seed', type=int, choices=range(1,21), help='Omit to run all twenty seeds')
    parser.add_argument('--output', type=Path, default=Path('/results'))
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve() / args.suite
    if not args.dry_run:
        if output.exists() and any(output.iterdir()):
            parser.error('Output suite directory is nonempty; choose a new output directory')
        output.mkdir(parents=True, exist_ok=True)
    for seed in ([args.seed] if args.seed else range(1,21)):
        for executable, options in commands(args.suite, seed):
            command = ['./ns3', 'run', f'scratch/{executable}', '--', *options, f'--outDir={output}']
            print(' '.join(command), flush=True)
            if not args.dry_run:
                subprocess.run(command, check=True)


if __name__ == '__main__':
    main()
