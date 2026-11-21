# Plan: Average of a list of numbers

**Status:** Approved

## Goal
The shop's reports show the average order value, which needs the mean of a list of amounts.

## Acceptance criteria
- [ ] `average(numbers)` in `src/calc.py` returns the arithmetic mean with true division: `average([2, 3])` is
      `2.5`.
- [ ] `average([])` raises `ValueError`.

## Files
- `src/calc.py`
- `tests/test_calc.py`

## Test plan
- Unit tests for each criterion, including a mean that is not a whole number.
