#!/bin/bash

# this assumes that all project dependencies, as well as all dev dependencies
# (e.g. flake8 and mypy) have already been installed, e.g. via:
#    pip install -r requrements.txt
#    pip install -r requrements-dev.txt

# flake8 and mypy config options are specified in setup.cfg

# set to a non-zero value if any check returns a non-zero value
check_result=0

echo "Run flake8 style checks"
echo "flake8 slack2discord.py slack2discord"
flake8 slack2discord.py slack2discord
flake8_result=$?
if [[ $flake8_result -eq 0 ]]; then
   echo "flake8: PASS"
else
   echo "flake8: FAIL"
   # will these colorize automatically?
   echo "Error"
   echo "ERROR"
   echo "Warning"
   echo "WARNING"
   check_result=1
fi

echo
echo "Run mypy static typing checks"
echo "mypy slack2discord.py"
mypy slack2discord.py
mypy_result=$?
if [[ $mypy_result -eq 0 ]]; then
   echo "mypy: PASS"
else
   echo "mypy: FAIL"
   # will these colorize automatically?
   echo "Error"
   echo "ERROR"
   echo "Warning"
   echo "WARNING"
   check_result=1
fi

echo
if [[ $check_result -eq 0 ]]; then
   echo "Union of all checks: PASS"
else
   echo "Union of all checks: FAIL"
   # will these colorize automatically?
   echo "Error"
   echo "ERROR"
   echo "Warning"
   echo "WARNING"
fi

exit $check_result
