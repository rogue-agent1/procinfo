#!/usr/bin/env python3
"""procinfo - Process inspector and stats.

One file. Zero deps. Know what's running.

Usage:
  procinfo.py list                → top processes by CPU
  procinfo.py list --sort mem     → top by memory
  procinfo.py find python         → find matching processes
  procinfo.py tree                → process tree
  procinfo.py pid 1234            → details for PID
  procinfo.py ports               → listening ports
  procinfo.py stats               → system process stats
"""

import argparse
import json
import os
import platform
import re
import subprocess
import sys


def run(cmd: str) -> str:
    try:
        env = os.environ.copy()
        env["PATH"] = "/usr/sbin:/usr/bin:/bin:/sbin:" + env.get("PATH", "")
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10, env=env)
        return r.stdout.strip()
    except Exception:
        return ""


def cmd_list(args):
    sort = args.sort or "cpu"
    n = args.n or 15
    if sort == "cpu":
        out = run(f"ps aux --sort=-%cpu 2>/dev/null || ps aux -r")
    else:
        out = run(f"ps aux --sort=-%mem 2>/dev/null || ps aux -m")
    lines = out.split("\n")
    if not lines:
        return 1
    print(f"{'PID':>7} {'CPU%':>5} {'MEM%':>5} {'RSS':>8}  {'COMMAND'}")
    for line in lines[1:n+1]:
        parts = line.split(None, 10)
        if len(parts) < 11:
            continue
        pid, cpu, mem, rss, cmd = parts[1], parts[2], parts[3], parts[5], parts[10]
        cmd_short = cmd[:60]
        print(f"{pid:>7} {cpu:>5} {mem:>5} {rss:>8}  {cmd_short}")


def cmd_find(args):
    out = run(f"ps aux")
    pattern = args.pattern.lower()
    lines = out.split("\n")
    found = 0
    for line in lines[1:]:
        if pattern in line.lower():
            parts = line.split(None, 10)
            if len(parts) >= 11:
                print(f"  PID {parts[1]:>7}  CPU {parts[2]:>5}%  MEM {parts[3]:>5}%  {parts[10][:70]}")
                found += 1
    if not found:
        print(f"No processes matching '{args.pattern}'")
        return 1


def cmd_pid(args):
    out = run(f"ps -p {args.pid} -o pid,ppid,%cpu,%mem,rss,vsz,etime,command")
    if not out or len(out.split("\n")) < 2:
        print(f"PID {args.pid} not found")
        return 1
    lines = out.split("\n")
    header = lines[0].split()
    values = lines[1].split(None, len(header) - 1)
    for h, v in zip(header, values):
        print(f"  {h:12s} {v}")
    # Open files
    if platform.system() == "Darwin":
        fds = run(f"lsof -p {args.pid} 2>/dev/null | wc -l").strip()
        print(f"  {'OPEN_FILES':12s} {fds}")


def cmd_ports(args):
    if platform.system() == "Darwin":
        out = run("lsof -i -P -n | grep LISTEN")
    else:
        out = run("ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null")
    if not out:
        print("No listening ports found")
        return
    lines = out.split("\n")
    seen = set()
    for line in lines[:30]:
        parts = line.split()
        if platform.system() == "Darwin" and len(parts) >= 9:
            proc = parts[0]
            pid = parts[1]
            addr = parts[8]
            key = f"{pid}:{addr}"
            if key not in seen:
                seen.add(key)
                print(f"  {proc:20s} PID {pid:>7}  {addr}")
        else:
            print(f"  {line.strip()}")


def cmd_stats(args):
    out = run("ps aux")
    lines = out.split("\n")[1:]
    total = len(lines)
    total_cpu = sum(float(l.split()[2]) for l in lines if len(l.split()) > 2)
    total_mem = sum(float(l.split()[3]) for l in lines if len(l.split()) > 3)
    zombies = sum(1 for l in lines if len(l.split()) > 7 and l.split()[7] == "Z")
    print(f"  Total processes:  {total}")
    print(f"  Total CPU%:       {total_cpu:.1f}%")
    print(f"  Total MEM%:       {total_mem:.1f}%")
    print(f"  Zombie processes: {zombies}")
    load = os.getloadavg()
    print(f"  Load average:     {load[0]:.2f} {load[1]:.2f} {load[2]:.2f}")


def cmd_tree(args):
    out = run("ps -eo pid,ppid,comm")
    lines = out.split("\n")[1:]
    procs = {}
    children = {}
    for line in lines:
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        pid, ppid, cmd = int(parts[0]), int(parts[1]), parts[2].strip()
        procs[pid] = cmd
        children.setdefault(ppid, []).append(pid)

    def show(pid, prefix="", last=True):
        cmd = procs.get(pid, "?")[:50]
        connector = "└─ " if last else "├─ "
        print(f"{prefix}{connector}{pid} {cmd}")
        kids = children.get(pid, [])
        for i, kid in enumerate(kids[:20]):
            show(kid, prefix + ("   " if last else "│  "), i == len(kids) - 1)

    roots = [pid for pid in procs if procs.get(pid) and (pid == 1 or procs[pid].split("/")[-1] == "launchd")]
    for r in roots[:3]:
        show(r)


def main():
    p = argparse.ArgumentParser(description="Process inspector")
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("list")
    s.add_argument("--sort", choices=["cpu", "mem"], default="cpu")
    s.add_argument("-n", type=int, default=15)
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("find")
    s.add_argument("pattern")
    s.set_defaults(func=cmd_find)

    s = sub.add_parser("pid")
    s.add_argument("pid", type=int)
    s.set_defaults(func=cmd_pid)

    s = sub.add_parser("ports")
    s.set_defaults(func=cmd_ports)

    s = sub.add_parser("stats")
    s.set_defaults(func=cmd_stats)

    s = sub.add_parser("tree")
    s.set_defaults(func=cmd_tree)

    args = p.parse_args()
    if not args.cmd:
        p.print_help()
        return 1
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
