"""
Functions for printing logs for this project.
"""
import sys
from datetime import datetime


def print_arg(arg_name: str, arg_val: str):
    print(f'[ARG] {arg_name}: {arg_val}', file=sys.stderr)


def print_progress(msg: str):
    print(f'[{_get_curr_time()}, Progress] {msg}', file=sys.stderr)


def print_warn(msg: str):
    print(f'[{_get_curr_time()}, WARNING] {msg}', file=sys.stderr)


def print_err(msg: str):
    print(f'[{_get_curr_time()}, ERROR] {msg}', file=sys.stderr)


def _get_curr_time() -> str:
    now = datetime.now()
    curr_time = now.strftime('%H:%M:%S %m/%d/%y')
    return curr_time
